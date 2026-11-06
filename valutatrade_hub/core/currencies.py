from abc import ABC, abstractmethod

from valutatrade_hub.core.exceptions import CurrencyNotFoundError


class Currency(ABC):
    def __init__(self, name: str, code: str):
        self.code = code
        self.name = name

    @property
    def code(self) -> str:
        return self._code

    @code.setter
    def code(self, value: str) -> None:
        if (
            not isinstance(value, str)
            or not 2 <= len(value) <= 5
            or any(character.isspace() for character in value)
            or not value.isupper()
        ):
            raise ValueError("Код валюты: 2–5 символов в верхнем регистре, без пробелов")
        self._code = value

    @property
    def name(self) -> str:
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Название валюты не должно быть пустым")
        self._name = value.strip()

    @abstractmethod
    def get_display_info(self) -> str:
        pass


class FiatCurrency(Currency):
    def __init__(self, name: str, code: str, issuing_country: str):
        super().__init__(name, code)
        self.issuing_country = issuing_country

    def get_display_info(self) -> str:
        return f"[FIAT] {self.code} — {self.name} (Issuing: {self.issuing_country})"


class CryptoCurrency(Currency):
    def __init__(self, name: str, code: str, algorithm: str, market_cap: float):
        super().__init__(name, code)
        self.algorithm = algorithm
        self.market_cap = market_cap

    def get_display_info(self) -> str:
        market_cap = f"{self.market_cap:.3g}".replace("e+", "e")
        return (
            f"[CRYPTO] {self.code} — {self.name} "
            f"(Algo: {self.algorithm}, MCAP: {market_cap})"
        )


_CURRENCIES = {
    "USD": FiatCurrency("US Dollar", "USD", "United States"),
    "EUR": FiatCurrency("Euro", "EUR", "Eurozone"),
    "GBP": FiatCurrency("Pound Sterling", "GBP", "United Kingdom"),
    "RUB": FiatCurrency("Russian Ruble", "RUB", "Russia"),
    "BTC": CryptoCurrency("Bitcoin", "BTC", "SHA-256", 1.12e12),
    "ETH": CryptoCurrency("Ethereum", "ETH", "Ethash", 0.0),
    "SOL": CryptoCurrency("Solana", "SOL", "PoS", 0.0),
}


def get_currency(code: str) -> Currency:
    if not isinstance(code, str) or code not in _CURRENCIES:
        raise CurrencyNotFoundError(code)

    return _CURRENCIES[code]
