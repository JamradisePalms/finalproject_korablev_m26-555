import math
from datetime import datetime

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    AuthenticationError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Portfolio, User, Wallet
from valutatrade_hub.core.utils import (
    get_pair_quote,
    get_pair_rate,
    is_rate_stale,
    load_json,
    save_json,
    validate_amount,
)
from valutatrade_hub.decorators import log_action
from valutatrade_hub.infra.settings import SettingsLoader
from valutatrade_hub.parser_service.api_clients import (
    CoinGeckoClient,
    ExchangeRateApiClient,
)
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage
from valutatrade_hub.parser_service.updater import RatesUpdater


def register(username: str, password: str) -> None:
    """Регистрирует пользователя и создаёт пустой портфель."""
    users = load_json("users.json")

    if any(user["username"] == username for user in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    portfolios = load_json("portfolios.json")

    user_id = max((item["user_id"] for item in users + portfolios), default=0) + 1
    user = User.create(user_id, username, password)
    users.append(
        {
            "username": user.username,
            "hashed_password": user.hashed_password,
            "salt": user.salt,
            "user_id": user.user_id,
            "registration_date": user.registration_date.isoformat(),
        }
    )
    portfolios.append({"user_id": user.user_id, "wallets": {}})

    save_json("users.json", users)
    save_json("portfolios.json", portfolios)

    print(
        f"Пользователь {username} успешно зарегистрирован (id={user_id}). "
        f"Войдите login --username {username} --password ***"
    )


def user_from_record(record: dict) -> User:
    return User(
        user_id=record["user_id"],
        username=record["username"],
        hashed_password=record["hashed_password"],
        salt=record["salt"],
        registration_date=datetime.fromisoformat(record["registration_date"]),
    )


def login(username: str, password: str) -> User:
    """Проверяет пароль и возвращает пользователя для текущего сеанса."""
    users = load_json("users.json")

    record = next((item for item in users if item["username"] == username), None)
    if record is None:
        raise AuthenticationError(f"Пользователь '{username}' не найден")

    user = user_from_record(record)
    if not user.verify_password(password):
        raise AuthenticationError("Неверный пароль")

    print(f"Вы вошли как '{user.username}'")
    return user


def show_portfolio(user: User | None, base_currency: str | None = None) -> None:
    """Выводит кошельки и общую стоимость в выбранной валюте."""
    user, _, portfolio_record = _get_portfolio(user)

    if base_currency is None:
        base_currency = SettingsLoader().get("base_currency")
    get_currency(base_currency)

    wallet_records = portfolio_record["wallets"]
    if not wallet_records:
        print("Портфель пуст")
        return

    wallets = {code: _wallet(wallet_records, code) for code in wallet_records}
    portfolio = Portfolio(user, wallets)

    rates = load_json("rates.json")
    total = portfolio.get_total_value(rates, base_currency)

    print(f"Портфель пользователя: {portfolio.user.username} (база: {base_currency}):")
    for code, wallet in wallets.items():
        amount = wallet.balance
        value = amount * get_pair_rate(rates, code, base_currency)
        print(f"- {code}: {amount} -> {value} {base_currency}")

    print(f"ИТОГО: {total} {base_currency}")


def _get_portfolio(user: User | None) -> tuple[User, list[dict], dict]:
    if user is None:
        raise AuthenticationError("Используйте команду login для входа в аккаунт")

    user_id = user.user_id
    portfolios = load_json("portfolios.json")
    portfolio = next((item for item in portfolios if item["user_id"] == user_id), None)

    if portfolio is None:
        raise ValueError(f"Портфель пользователя с id={user_id} не найден")

    return user, portfolios, portfolio


def _trade_context(
    user: User | None, currency_code: str, amount: float
) -> tuple[list[dict], dict, float, float]:

    _, portfolios, portfolio = _get_portfolio(user)

    validate_amount(amount)

    get_currency(currency_code)
    rates = load_json("rates.json")

    quote = get_pair_quote(rates, currency_code, "USD")

    if is_rate_stale(quote):
        raise ApiRequestError(
            f"Курс {currency_code}->USD устарел. Выполните update-rates перед сделкой"
        )

    rate = quote["rate"]

    value = amount * rate
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Стоимость сделки должна быть конечным положительным числом")

    return portfolios, portfolio, rate, value


def _wallet(wallets: dict, currency_code: str) -> Wallet:
    balance = wallets.get(currency_code, {}).get("balance", 0.0)

    if isinstance(balance, bool) or not isinstance(balance, (int, float)):
        raise TypeError(f"Некорректный баланс кошелька {currency_code}")

    return Wallet(currency_code, float(balance))


@log_action(verbose=True)
def buy(user: User | None, currency_code: str, amount: float) -> dict:
    """Покупает валюту за USD по свежей котировке из кеша."""
    portfolios, portfolio, rate, cost = _trade_context(user, currency_code, amount)

    wallets = portfolio["wallets"]
    usd_wallet = _wallet(wallets, "USD")

    currency_wallet = (
        usd_wallet if currency_code == "USD" else _wallet(wallets, currency_code)
    )

    if cost > usd_wallet.balance:
        raise InsufficientFundsError(usd_wallet.balance, cost, "USD")

    before = currency_wallet.balance

    if currency_code != "USD":
        usd_wallet.withdraw(cost)
        currency_wallet.deposit(amount)

        if not math.isfinite(currency_wallet.balance):
            raise ValueError("Баланс после покупки должен быть конечным числом")

    wallets.setdefault("USD", {"currency_code": "USD"})["balance"] = usd_wallet.balance
    wallets.setdefault(currency_code, {"currency_code": currency_code})["balance"] = (
        currency_wallet.balance
    )

    save_json("portfolios.json", portfolios)

    print(
        f"Покупка выполнена: {amount:.4f} {currency_code} "
        f"по курсу {rate:.4f} USD/{currency_code}\n"
        f"- {currency_code}: было {before:.4f} -> стало {currency_wallet.balance:.4f}\n"
        f"Списано: {cost:.2f} USD"
    )
    return {
        "rate": rate,
        "base": "USD",
        "before": before,
        "after": currency_wallet.balance,
    }


@log_action(verbose=True)
def sell(user: User | None, currency_code: str, amount: float) -> dict:
    """Продаёт валюту за USD по свежей котировке из кеша."""
    portfolios, portfolio, rate, proceeds = _trade_context(user, currency_code, amount)

    wallets = portfolio["wallets"]
    if currency_code not in wallets:
        raise InsufficientFundsError(0.0, amount, currency_code)

    currency_wallet = _wallet(wallets, currency_code)
    usd_wallet = currency_wallet if currency_code == "USD" else _wallet(wallets, "USD")

    if amount > currency_wallet.balance:
        raise InsufficientFundsError(currency_wallet.balance, amount, currency_code)

    before = currency_wallet.balance

    if currency_code != "USD":
        currency_wallet.withdraw(amount)
        usd_wallet.deposit(proceeds)

        if not math.isfinite(usd_wallet.balance):
            raise ValueError("Баланс после продажи должен быть конечным числом")

    wallets[currency_code]["balance"] = currency_wallet.balance
    wallets.setdefault("USD", {"currency_code": "USD"})["balance"] = usd_wallet.balance

    save_json("portfolios.json", portfolios)

    print(
        f"Продажа выполнена: {amount:.4f} {currency_code} "
        f"по курсу {rate:.4f} USD/{currency_code}\n"
        f"- {currency_code}: было {before:.4f} -> стало {currency_wallet.balance:.4f}\n"
        f"Зачислено: {proceeds:.2f} USD"
    )
    return {
        "rate": rate,
        "base": "USD",
        "before": before,
        "after": currency_wallet.balance,
    }


def get_rate(from_currency: str, to_currency: str) -> dict:
    """Возвращает курс и время; при необходимости обновляет котировки."""
    get_currency(from_currency)
    get_currency(to_currency)

    try:
        rates = load_json("rates.json")
    except FileNotFoundError:
        rates = {}

    try:
        quote = get_pair_quote(rates, from_currency, to_currency)
        stale = is_rate_stale(quote)
    except ApiRequestError:
        stale = True

    if stale:
        config = ParserConfig(
            RATES_FILE_PATH=f"{SettingsLoader().get('data_dir')}/rates.json"
        )

        updater = RatesUpdater(
            config,
            [CoinGeckoClient(config), ExchangeRateApiClient(config)],
            RatesStorage(config),
        )

        try:
            rates = updater.run_update()["rates"]
        except (OSError, ValueError) as error:
            raise ApiRequestError(str(error)) from error

    quote = get_pair_quote(rates, from_currency, to_currency)
    if is_rate_stale(quote):
        raise ApiRequestError(
            f"Курс {from_currency}->{to_currency} устарел: источник не обновил данные"
        )
    print(
        f"Курс {from_currency}->{to_currency}: {quote['rate']} "
        f"(обновлено: {quote['updated_at']}, источник: {quote['source']})"
    )
    if from_currency != to_currency:
        reverse = get_pair_quote(rates, to_currency, from_currency)
        print(f"Обратный курс {to_currency}->{from_currency}: {reverse['rate']}")
    return {"rate": quote["rate"], "updated_at": quote["updated_at"]}


def deposit(user: User | None, amount: float) -> None:
    """Пополняет USD-кошелёк для симуляции торговли."""
    _, portfolios, portfolio = _get_portfolio(user)

    validate_amount(amount)

    wallets = portfolio["wallets"]
    usd_wallet = _wallet(wallets, "USD")
    usd_wallet.deposit(amount)

    if not math.isfinite(usd_wallet.balance):
        raise ValueError("Баланс после пополнения должен быть конечным числом")

    wallets.setdefault("USD", {"currency_code": "USD"})["balance"] = usd_wallet.balance

    save_json("portfolios.json", portfolios)

    print(f"Зачислено: {amount:.2f} USD. Баланс: {usd_wallet.balance:.2f} USD")


def update_rates(source: str | None = None) -> dict:
    """Запускает обновление выбранных источников и выводит результат."""
    config = ParserConfig()

    client_types = {
        "coingecko": CoinGeckoClient,
        "exchangerate": ExchangeRateApiClient,
    }

    if source is not None and source not in client_types:
        raise ValueError(f"Неизвестный источник '{source}'")

    selected = [client_types[source]] if source else list(client_types.values())

    updater = RatesUpdater(
        config, [client(config) for client in selected], RatesStorage(config)
    )

    result = updater.run_update()

    print(
        f"Обновлено курсов: {result['updated_count']}. "
        f"Последнее обновление: {result['last_refresh']}"
    )

    if result["errors"]:
        print(
            "Обновление завершено с ошибками: "
            + ", ".join(result["errors"])
            + ". Подробности в logs/parser.log."
        )

    return result


def show_rates(
    currency: str | None = None, top: int | None = None, base: str | None = None
) -> None:
    """Выводит котировки из кеша с фильтрами и предупреждением о давности."""
    if top is not None and top <= 0:
        raise ValueError("--top должен быть положительным числом")

    try:
        rates = load_json("rates.json")
    except FileNotFoundError:
        rates = {"pairs": {}}

    if not isinstance(rates, dict) or not isinstance(rates.get("pairs"), dict):
        raise TypeError("Некорректный формат кеша курсов: ожидается словарь pairs")

    pairs = rates["pairs"]
    if not pairs:
        print(
            "Локальный кеш курсов пуст. Выполните 'update-rates', чтобы загрузить данные."
        )
        return

    codes = {code for pair in pairs for code in pair.split("_")}

    base = base or SettingsLoader().get("base_currency")
    if base not in codes:
        raise ValueError(f"Курс для '{base}' не найден в кеше")

    if currency is not None and currency not in codes:
        raise ValueError(f"Курс для '{currency}' не найден в кеше")

    config = ParserConfig()
    rows = []

    for code in codes:
        if currency is not None and code != currency:
            continue

        if top is not None and code not in config.CRYPTO_CURRENCIES:
            continue

        if code == base and currency is None:
            continue

        quote = get_pair_quote(rates, code, base)
        rows.append((code, quote))

    rows.sort(
        key=lambda row: row[1]["rate"] if top is not None else row[0],
        reverse=top is not None,
    )

    if top is not None:
        rows = rows[:top]

    if not rows:
        print("Курсы по заданным фильтрам не найдены в кеше.")
        return

    print(
        f"Курсы из кеша (последнее обновление: {rates.get('last_refresh', 'неизвестно')}):"
    )

    if any(is_rate_stale(quote) for _, quote in rows):
        print("Внимание: есть устаревшие курсы. Выполните update-rates.")

    table = PrettyTable(["Пара", "Курс", "Обновлено", "Источник"])
    table.align = "l"
    for code, quote in rows:
        table.add_row(
            [
                f"{code}_{base}",
                f"{quote['rate']:.10g}",
                quote["updated_at"],
                quote["source"],
            ]
        )

    print(table)
