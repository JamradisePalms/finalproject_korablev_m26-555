import hashlib
import math
import secrets
from copy import deepcopy
from datetime import datetime

from valutatrade_hub.core.exceptions import InsufficientFundsError

CURRENCIES = {
    "USD": 1.0,
    "EUR": 1.1,
    "RUB": 0.01,
    "BTC": 1000.0,
    "ETH": 2000.0,
}

class User:
    def __init__(self, user_id: int, username: str, hashed_password: str, salt: str, registration_date: datetime):
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._registration_date = registration_date
        self._salt = salt

    @property
    def user_id(self) -> int:
        return self._user_id

    @property
    def username(self) -> str:
        return self._username

    @property
    def registration_date(self) -> datetime:
        return self._registration_date

    @property
    def hashed_password(self) -> str:
        return self._hashed_password

    @property
    def salt(self) -> str:
        return self._salt

    @username.setter
    def username(self, new_username: str) -> None:
        if not new_username.strip():
            raise ValueError("Username cannot be empty")

        self._username = new_username

    def get_user_info(self) -> str:
        return f"User ID: {self._user_id}, Username: {self._username}, Registration Date: {self._registration_date}"

    def change_password(self, new_password: str) -> None:
        if len(new_password) < 4:
            raise ValueError("Password must be at least 4 characters long")

        self._salt = secrets.token_hex(16)
        self._hashed_password = hashlib.sha256((new_password + self._salt).encode("utf-8")).hexdigest()
        print(f"Password changed for user {self._username}")

    def verify_password(self, password: str) -> bool:
        return hashlib.sha256((password + self._salt).encode("utf-8")).hexdigest() == self._hashed_password


class Wallet:
    def __init__(self, currency_code: str, balance: float = 0.0):
        self._currency_code = currency_code
        self.balance = balance

    @property
    def balance(self) -> float:
        return self._balance

    @balance.setter
    def balance(self, new_balance: float) -> None:
        if not isinstance(new_balance, float):
            raise TypeError("Баланс должен быть числом")

        if not math.isfinite(new_balance) or new_balance < 0:
            raise ValueError("Баланс должен быть конечным неотрицательным числом")

        self._balance = new_balance

    def deposit(self, amount: float) -> None:
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Сумма должна быть конечным положительным числом")

        self._balance += amount

    def withdraw(self, amount: float) -> None:
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Сумма должна быть конечным положительным числом")

        if amount > self._balance:
            raise InsufficientFundsError(self._balance, amount, self._currency_code)

        self._balance -= amount

    def get_balance_info(self) -> float:
        return self._balance


class Portfolio:
    def __init__(self, user: User, wallets: dict[str, Wallet]):
        self._user = user
        self._user_id = self._user.user_id
        self._wallets = wallets

    @property
    def user(self) -> User:
        return self._user

    @property
    def wallets(self) -> dict[str, Wallet]:
        return deepcopy(self._wallets)

    def add_currency(self, currency_code: str) -> None:
        if currency_code in self._wallets:
            raise ValueError(f"Кошелек для валюты {currency_code} уже существует")

        self._wallets[currency_code] = Wallet(currency_code)

    def get_wallet(self, currency_code: str) -> Wallet:
        if currency_code not in self._wallets:
            raise ValueError(f"У вас нет кошелька '{currency_code}'")

        return self._wallets[currency_code]

    def get_total_value(self, base_currency: str = "USD") -> float:
        total_value = 0.0

        if base_currency not in CURRENCIES:
            raise ValueError(f"Неизвестная валюта: {base_currency}")

        base_currency_value = CURRENCIES[base_currency]

        for wallet in self._wallets.values():
            if wallet._currency_code not in CURRENCIES:
                raise ValueError(f"Неизвестная валюта: {wallet._currency_code}")

            total_value += wallet.get_balance_info() * CURRENCIES[wallet._currency_code] / base_currency_value

        return total_value
