import hashlib
import math
import secrets
from copy import deepcopy
from datetime import datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import get_pair_rate


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
        """Задаёт непустое имя пользователя."""
        if not new_username.strip():
            raise ValueError("Username cannot be empty")

        self._username = new_username

    def get_user_info(self) -> str:
        """Возвращает сведения о пользователе."""
        return f"User ID: {self._user_id}, Username: {self._username}, Registration Date: {self._registration_date}"

    def change_password(self, new_password: str) -> None:
        """Заменяет текущий пароль на новый."""
        if len(new_password) < 4:
            raise ValueError("Password must be at least 4 characters long")

        self._salt = secrets.token_hex(16)
        self._hashed_password = hashlib.sha256((new_password + self._salt).encode("utf-8")).hexdigest()
        print(f"Password changed for user {self._username}")

    def verify_password(self, password: str) -> bool:
        """Сравнивает переданный пароль с сохранённым."""
        return hashlib.sha256((password + self._salt).encode("utf-8")).hexdigest() == self._hashed_password


class Wallet:
    def __init__(self, currency_code: str, balance: float = 0.0):
        self._currency_code = currency_code
        self.balance = balance

    @property
    def currency_code(self) -> str:
        return self._currency_code

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
        """Увеличивает баланс на положительную конечную сумму."""
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Сумма должна быть конечным положительным числом")

        self._balance += amount

    def withdraw(self, amount: float) -> None:
        """Списывает сумму, проверяя достаточность средств."""
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
        """Создаёт кошелёк и проверяет повторное добавление валюты."""
        if currency_code in self._wallets:
            raise ValueError(f"Кошелек для валюты {currency_code} уже существует")

        self._wallets[currency_code] = Wallet(currency_code)

    def get_wallet(self, currency_code: str) -> Wallet:
        """Возвращает кошелёк выбранной валюты."""
        if currency_code not in self._wallets:
            raise ValueError(f"У вас нет кошелька '{currency_code}'")

        return self._wallets[currency_code]

    def get_total_value(self, rates: dict, base_currency: str = "USD") -> float:
        """Возвращает текущую стоимость портфеля."""
        get_currency(base_currency)

        total_value = 0.0
        for code, wallet in self._wallets.items():
            total_value += wallet.balance * get_pair_rate(rates, code, base_currency)

        if not math.isfinite(total_value):
            raise ValueError("Стоимость портфеля должна быть конечным числом")

        return total_value
