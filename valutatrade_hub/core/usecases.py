import hashlib
import math
import secrets
from datetime import datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import (
    ApiRequestError,
    AuthenticationError,
    InsufficientFundsError,
)
from valutatrade_hub.core.models import Wallet
from valutatrade_hub.core.utils import (
    get_mock_rates,
    get_pair_rate,
    load_json,
    save_json,
    validate_amount,
)


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


def show_portfolio(user_id: str | None, base_currency: str = "USD") -> None:
    user, _, portfolio = _get_portfolio(user_id)

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


def buy(user_id: str | None, currency_code: str, amount: float) -> None:
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


def sell(user_id: str | None, currency_code: str, amount: float) -> None:
    portfolios, portfolio, rate, proceeds = _trade_context(
        user_id, currency_code, amount
    )

    wallets = portfolio["wallets"]
    if currency_code not in wallets:
        raise ValueError(f"У вас нет кошелька '{currency_code}'")

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


def get_rate(from_currency: str, to_currency: str) -> None:
    get_currency(from_currency)
    get_currency(to_currency)

    try:
        rates = load_json("rates.json")
    except FileNotFoundError:
        rates = {}

    now = datetime.now().astimezone()
    try:
        updated_at = datetime.fromisoformat(rates.get("last_refresh", "")).astimezone()
        stale = not 0 <= (now - updated_at).total_seconds() < 300
    except (ValueError, TypeError):
        stale = True

    if stale:
        try:
            rates = get_mock_rates()
        except (OSError, ValueError) as error:
            raise ApiRequestError(str(error)) from error
        rates["last_refresh"] = now.isoformat()

    rate = get_pair_rate(rates, from_currency, to_currency)

    if stale:
        save_json("rates.json", rates)

    print(
        f"Курс {from_currency}->{to_currency}: {rate} "
        f"(обновлено: {rates['last_refresh']})"
    )

    if from_currency != to_currency:
        reverse = rates.get(to_currency, {}).get(from_currency)
        if (
            not isinstance(reverse, bool)
            and isinstance(reverse, (int, float))
            and math.isfinite(reverse)
            and reverse > 0
        ):
            print(f"Обратный курс {to_currency}->{from_currency}: {reverse}")


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
