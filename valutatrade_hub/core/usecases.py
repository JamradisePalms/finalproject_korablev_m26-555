import hashlib
import math
import secrets
from datetime import datetime

from prettytable import PrettyTable

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    AuthenticationError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Wallet
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
    users = load_json("users.json")

    if any(user["username"] == username for user in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    if not username.strip():
        raise ValueError("Имя пользователя не может быть пустым")

    if len(password) < 4:
        raise ValueError("Пароль должен быть не короче 4 символов")

    portfolios = load_json("portfolios.json")

    user_id = (
        max(
            (
                item["user_id"]
                for item in users + portfolios
                if isinstance(item["user_id"], int)
            ),
            default=0,
        )
        + 1
    )
    salt = secrets.token_hex(16)
    hashed_password = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    users.append(
        {
            "username": username,
            "hashed_password": hashed_password,
            "salt": salt,
            "user_id": user_id,
            "registration_date": datetime.now().isoformat(),
        }
    )
    portfolios.append({"user_id": user_id, "wallets": {}})

    save_json("users.json", users)
    save_json("portfolios.json", portfolios)

    print(
        f"Пользователь {username} успешно зарегистрирован (id={user_id}). "
        f"Войдите login --username {username} --password ***"
    )


def login(username: str, password: str) -> str | int:
    users = load_json("users.json")

    user = next((item for item in users if item["username"] == username), None)

    if user is None:
        raise AuthenticationError(f"Пользователь '{username}' не найден")

    hashed_password = hashlib.sha256(
        (password + user["salt"]).encode("utf-8")
    ).hexdigest()

    if hashed_password != user["hashed_password"]:
        raise AuthenticationError("Неверный пароль")

    print(f"Вы вошли как '{username}'")
    return user["user_id"]


def show_portfolio(user_id: str | None, base_currency: str | None = None) -> None:
    user, _, portfolio = _get_portfolio(user_id)

    if base_currency is None:
        base_currency = SettingsLoader().get("base_currency")
    get_currency(base_currency)

    wallets = portfolio["wallets"]

    if not wallets:
        print("Портфель пуст")
        return

    rates = load_json("rates.json")

    print(f"Портфель пользователя: {user['username']} (база: {base_currency}):")

    total = 0.0
    for code, wallet in wallets.items():
        amount = wallet["balance"]
        value = amount * get_pair_rate(rates, code, base_currency)
        total += value
        print(f"- {code}: {amount} -> {value} {base_currency}")

    print(f"ИТОГО: {total} {base_currency}")


def _get_portfolio(user_id: str | None) -> tuple[dict, list[dict], dict]:
    if user_id is None:
        raise AuthenticationError("Используйте команду login для входа в аккаунт")

    users = load_json("users.json")
    user = next((item for item in users if item["user_id"] == user_id), None)

    if user is None:
        raise ValueError(f"Пользователь с id={user_id} не найден")

    portfolios = load_json("portfolios.json")
    portfolio = next((item for item in portfolios if item["user_id"] == user_id), None)

    if portfolio is None:
        raise ValueError(f"Портфель пользователя с id={user_id} не найден")

    return user, portfolios, portfolio


def _trade_context(
    user_id: str | None, currency_code: str, amount: float
) -> tuple[list[dict], dict, float, float]:

    _, portfolios, portfolio = _get_portfolio(user_id)

    validate_amount(amount)

    rates = load_json("rates.json")
    rate = get_pair_rate(rates, currency_code, "USD")

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
def buy(user_id: str | None, currency_code: str, amount: float) -> dict:
    portfolios, portfolio, rate, cost = _trade_context(user_id, currency_code, amount)

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
def sell(user_id: str | None, currency_code: str, amount: float) -> dict:
    portfolios, portfolio, rate, proceeds = _trade_context(
        user_id, currency_code, amount
    )

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


def deposit(user_id: str | None, amount: float) -> None:
    _, portfolios, portfolio = _get_portfolio(user_id)

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
