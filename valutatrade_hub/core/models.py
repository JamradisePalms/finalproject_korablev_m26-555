import hashlib
import math
import secrets
from copy import deepcopy
from datetime import datetime

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import InsufficientFundsError
from valutatrade_hub.core.utils import get_pair_rate, validate_amount


class User:
    def __init__(
        self,
        user_id: int,
        username: str,
        hashed_password: str,
        salt: str,
        registration_date: datetime,
    ):
        self._user_id = user_id
        self.username = username
        self._hashed_password = hashed_password
        self._registration_date = registration_date
        self._salt = salt

    @classmethod
    def create(cls, user_id: int, username: str, password: str) -> "User":
        """Создаёт пользователя и подготавливает данные для хранения пароля."""
        user = cls(user_id, username, "", "", datetime.now())
        user._set_password(password)
        return user

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
            raise ValueError("Имя пользователя не может быть пустым")

        self._username = new_username

    def get_user_info(self) -> str:
        """Возвращает сведения о пользователе."""
        return f"User ID: {self._user_id}, Username: {self._username}, Registration Date: {self._registration_date}"

    def change_password(self, new_password: str) -> None:
        """Заменяет текущий пароль на новый."""
        self._set_password(new_password)
        print(f"Password changed for user {self._username}")

    def verify_password(self, password: str) -> bool:
        """Сравнивает хеш введённого пароля с сохранённым."""
        return self._hash_password(password, self._salt) == self._hashed_password

    def _set_password(self, password: str) -> None:
        if len(password) < 4:
            raise ValueError("Пароль должен быть не короче 4 символов")

        salt = secrets.token_hex(16)
        self._hashed_password = self._hash_password(password, salt)
        self._salt = salt

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.sha256((password + salt).encode("utf-8")).hexdigest()


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
        if isinstance(new_balance, bool) or not isinstance(new_balance, (int, float)):
            raise TypeError("Баланс должен быть числом")

        try:
            balance = float(new_balance)
        except OverflowError as error:
            raise ValueError("Баланс выходит за допустимый диапазон") from error

        if not math.isfinite(balance) or balance < 0:
            raise ValueError("Баланс должен быть конечным неотрицательным числом")

        self._balance = balance

    def deposit(self, amount: float) -> None:
        """Увеличивает баланс на положительную конечную сумму."""
        validate_amount(amount)
        self.balance += amount

    def withdraw(self, amount: float) -> None:
        """Списывает сумму, проверяя достаточность средств."""
        validate_amount(amount)

        if amount > self._balance:
            raise InsufficientFundsError(self._balance, amount, self._currency_code)

        self._balance -= amount

    def get_balance_info(self) -> str:
        """Возвращает баланс вместе с кодом валюты."""
        return f"{self.balance} {self.currency_code}"


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
        _, total_value = self.get_valuation(rates, base_currency)
        return total_value

    def get_valuation(
        self, rates: dict, base_currency: str = "USD"
    ) -> tuple[list[tuple[str, float, float]], float]:
        """Возвращает оценку каждого кошелька и общую стоимость портфеля."""
        get_currency(base_currency)

        rows = []
        total_value = 0.0
        for code, wallet in self._wallets.items():
            amount = wallet.balance
            value = amount * get_pair_rate(rates, code, base_currency)
            rows.append((code, amount, value))
            total_value += value

        if not math.isfinite(total_value):
            raise ValueError("Стоимость портфеля должна быть конечным числом")

        return rows, total_value
