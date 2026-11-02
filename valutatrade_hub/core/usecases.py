import hashlib
import json
import math
import secrets
from datetime import datetime

from valutatrade_hub.core.models import Wallet
from valutatrade_hub.core.utils import get_mock_rates


def register(username: str, password: str) -> None:
    with open("data/users.json", encoding="utf-8") as file:
        users = json.load(file)

    if any(user["username"] == username for user in users):
        raise ValueError(f"Имя пользователя '{username}' уже занято")

    if not username.strip():
        raise ValueError("Имя пользователя не может быть пустым")

    if len(password) < 4:
        raise ValueError("Пароль должен быть не короче 4 символов")

    with open("data/portfolios.json", encoding="utf-8") as file:
        portfolios = json.load(file)

    user_id = max(
        (item["user_id"] for item in users + portfolios
         if isinstance(item["user_id"], int)),
        default=0,
    ) + 1
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

    _save_json("users.json", users)
    _save_json("portfolios.json", portfolios)

    print(
        f"Пользователь {username} успешно зарегистрирован (id={user_id}). "
        f"Войдите login --username {username} --password ***"
    )


def login(username: str, password: str) -> str | int:
    with open("data/users.json", encoding="utf-8") as file:
        users = json.load(file)

    user = next((item for item in users if item["username"] == username), None)

    if user is None:
        raise ValueError(f"Пользователь '{username}' не найден")

    hashed_password = hashlib.sha256(
        (password + user["salt"]).encode("utf-8")
    ).hexdigest()

    if hashed_password != user["hashed_password"]:
        raise ValueError("Неверный пароль")

    print(f"Вы вошли как '{username}'")
    return user["user_id"]


def show_portfolio(user_id: str | None, base_currency: str = "USD") -> None:
    if user_id is None:
        raise ValueError("Используйте команду login для входа в аккаунт")

    with open("data/users.json", encoding="utf-8") as file:
        users = json.load(file)

    username = next(
        (user["username"] for user in users if user["user_id"] == user_id), None
    )

    if not username:
        raise ValueError(f"Пользователь с id={user_id} не найден")

    with open("data/portfolios.json", encoding="utf-8") as file:
        portfolios = json.load(file)

    user_portfolio = next(
        (portfolio for portfolio in portfolios if portfolio["user_id"] == user_id), None
    )
    if user_portfolio is None:
        raise ValueError(f"Портфель пользователя с id={user_id} не найден")

    wallets = user_portfolio["wallets"]

    if not wallets:
        print("Портфель пуст")
        return

    with open("data/rates.json", encoding="utf-8") as file:
        rates = json.load(file)

    if base_currency not in rates:
        raise ValueError(f"Неизвестная валюта: {base_currency}")

    print(f"Портфель пользователя: {username} (база: {base_currency}):")

    total = 0

    for currency_code, wallet in wallets.items():
        currency_amount = wallet["balance"]
        currency_rate = (
            1 if currency_code == base_currency else rates[currency_code][base_currency]
        )

        total += currency_amount * currency_rate

        print(
            f"- {currency_code}: {currency_amount} -> "
            f"{currency_amount * currency_rate} {base_currency}"
        )

    print(f"ИТОГО: {total} {base_currency}")


def _trade_context(
    user_id: str | None, currency_code: str, amount: float
) -> tuple[list[dict], dict, float, float]:

    if user_id is None:
        raise ValueError("Используйте команду login для входа в аккаунт")

    if (
        not isinstance(currency_code, str)
        or not currency_code
        or currency_code != currency_code.strip().upper()
    ):
        raise ValueError("Код валюты должен быть непустой строкой в верхнем регистре")

    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("'amount' должен быть конечным положительным числом")

    with open("data/users.json", encoding="utf-8") as file:
        users = json.load(file)

    if not any(user["user_id"] == user_id for user in users):
        raise ValueError(f"Пользователь с id={user_id} не найден")

    with open("data/portfolios.json", encoding="utf-8") as file:
        portfolios = json.load(file)

    portfolio = next((item for item in portfolios if item["user_id"] == user_id), None)

    if portfolio is None:
        raise ValueError(f"Портфель пользователя с id={user_id} не найден")

    with open("data/rates.json", encoding="utf-8") as file:
        rates = json.load(file)

    if currency_code not in rates:
        raise ValueError(f"Неизвестная валюта: {currency_code}")

    currency_rates = rates[currency_code]
    if not isinstance(currency_rates, dict):
        raise TypeError(f"Некорректные курсы валюты: {currency_code}")

    rate = 1.0 if currency_code == "USD" else currency_rates.get("USD")

    if (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or rate <= 0
    ):
        raise ValueError(f"Не удалось получить курс для {currency_code}->USD")

    value = amount * rate
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Стоимость сделки должна быть конечным положительным числом")

    return portfolios, portfolio, rate, value


def _wallet(wallets: dict, currency_code: str) -> Wallet:
    balance = wallets.get(currency_code, {}).get("balance", 0.0)
    if isinstance(balance, bool) or not isinstance(balance, (int, float)):
        raise TypeError(f"Некорректный баланс кошелька {currency_code}")
    return Wallet(currency_code, float(balance))


def _save_json(filename: str, records: list[dict]) -> None:
    with open(f"data/{filename}", "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2, allow_nan=False)


def buy(user_id: str | None, currency_code: str, amount: float) -> None:
    portfolios, portfolio, rate, cost = _trade_context(user_id, currency_code, amount)

    wallets = portfolio["wallets"]
    usd_wallet = _wallet(wallets, "USD")

    currency_wallet = (
        usd_wallet if currency_code == "USD" else _wallet(wallets, currency_code)
    )

    if cost > usd_wallet.balance:
        raise ValueError(
            f"Недостаточно средств: доступно {usd_wallet.balance:.2f} USD, "
            f"требуется {cost:.2f} USD"
        )

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

    _save_json("portfolios.json", portfolios)

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
        raise ValueError(
            f"Недостаточно средств: доступно {currency_wallet.balance:.4f} "
            f"{currency_code}, требуется {amount:.4f} {currency_code}"
        )

    before = currency_wallet.balance

    if currency_code != "USD":
        currency_wallet.withdraw(amount)
        usd_wallet.deposit(proceeds)

        if not math.isfinite(usd_wallet.balance):
            raise ValueError("Баланс после продажи должен быть конечным числом")

    wallets[currency_code]["balance"] = currency_wallet.balance
    wallets.setdefault("USD", {"currency_code": "USD"})["balance"] = usd_wallet.balance

    _save_json("portfolios.json", portfolios)

    print(
        f"Продажа выполнена: {amount:.4f} {currency_code} "
        f"по курсу {rate:.4f} USD/{currency_code}\n"
        f"- {currency_code}: было {before:.4f} -> стало {currency_wallet.balance:.4f}\n"
        f"Зачислено: {proceeds:.2f} USD"
    )


def get_rate(from_currency: str, to_currency: str) -> None:

    for currency in (from_currency, to_currency):
        if (
            not isinstance(currency, str)
            or not currency
            or currency != currency.strip().upper()
        ):
            raise ValueError("Код валюты должен быть непустой строкой в верхнем регистре")

    try:
        with open("data/rates.json", encoding="utf-8") as file:
            rates = json.load(file)
    except FileNotFoundError:
        rates = {}

    now = datetime.now().astimezone()

    try:
        updated_at = datetime.fromisoformat(rates.get("last_refresh", "")).astimezone()

        age = (now - updated_at).total_seconds()

        stale = not 0 <= age < 300

    except (ValueError, TypeError):
        stale = True

    if stale:
        rates = get_mock_rates()
        rates["last_refresh"] = now.isoformat()

    for currency in (from_currency, to_currency):

        if currency not in rates or not isinstance(rates[currency], dict):
            raise ValueError(f"Неизвестная валюта: {currency}")

    rate = 1.0 if from_currency == to_currency else rates[from_currency].get(to_currency)

    if (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or rate <= 0
    ):
        raise ValueError(f"Курс {from_currency}->{to_currency} недоступен")

    if stale:
        _save_json("rates.json", rates)

    updated = rates["last_refresh"]

    print(f"Курс {from_currency}->{to_currency}: {rate} (обновлено: {updated})")

    if from_currency != to_currency:
        reverse_rate = rates[to_currency].get(from_currency)

        if (
            not isinstance(reverse_rate, bool)
            and isinstance(reverse_rate, (int, float))
            and math.isfinite(reverse_rate)
            and reverse_rate > 0
        ):
            print(f"Обратный курс {to_currency}->{from_currency}: {reverse_rate}")


def deposit(user_id: str | None, amount: float) -> None:

    if user_id is None:
        raise ValueError("Используйте команду login для входа в аккаунт")

    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("Сумма должна быть конечным положительным числом")

    with open("data/users.json", encoding="utf-8") as file:
        users = json.load(file)

    if not any(user["user_id"] == user_id for user in users):
        raise ValueError(f"Пользователь с id={user_id} не найден")

    with open("data/portfolios.json", encoding="utf-8") as file:
        portfolios = json.load(file)

    portfolio = next((item for item in portfolios if item["user_id"] == user_id), None)

    if portfolio is None:
        raise ValueError(f"Портфель пользователя с id={user_id} не найден")

    wallets = portfolio["wallets"]

    usd_wallet = _wallet(wallets, "USD")

    usd_wallet.deposit(amount)

    if not math.isfinite(usd_wallet.balance):
        raise ValueError("Баланс после пополнения должен быть конечным числом")

    wallets.setdefault("USD", {"currency_code": "USD"})["balance"] = usd_wallet.balance

    _save_json("portfolios.json", portfolios)

    print(f"Зачислено: {amount:.2f} USD. Баланс: {usd_wallet.balance:.2f} USD")
