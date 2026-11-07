import math
from abc import ABC, abstractmethod

import requests

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.config import ParserConfig


class BaseApiClient(ABC):
    def __init__(self, config: ParserConfig | None = None):
        self.config = config if config is not None else ParserConfig()

    @staticmethod
    def validate_rate(value, pair: str) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ApiRequestError(f"Некорректный курс {pair}")

        return float(value)

    @abstractmethod
    def fetch_rates(self) -> dict:
        pass

    def get_json(self, url: str, params: dict | None = None) -> dict:
        """Выполняет GET-запрос."""
        service = type(self).__name__

        try:
            response = requests.get(
                url, params=params, timeout=self.config.REQUEST_TIMEOUT
            )
            response.raise_for_status()

        except requests.exceptions.HTTPError as error:
            raise ApiRequestError(
                f"{service}: HTTP {error.response.status_code}"
            ) from None

        except requests.exceptions.RequestException as error:
            raise ApiRequestError(
                f"{service}: ошибка сети ({type(error).__name__})"
            ) from None

        try:
            data = response.json()

        except ValueError:
            raise ApiRequestError(f"{service}: ответ не является JSON") from None

        if not isinstance(data, dict):
            raise ApiRequestError(f"{service}: некорректная структура ответа")

        return data


class CoinGeckoClient(BaseApiClient):

    def fetch_rates(self) -> dict:
        """Возвращает котировки из CoinGecko."""
        base = self.config.BASE_FIAT_CURRENCY

        try:
            ids = {
                code: self.config.CRYPTO_ID_MAP[code]
                for code in self.config.CRYPTO_CURRENCIES
            }

        except KeyError as error:

            raise ApiRequestError(
                f"Не задан CoinGecko ID для {error.args[0]}"
            ) from None

        data = self.get_json(
            self.config.COINGECKO_URL,
            params={"ids": ",".join(ids.values()), "vs_currencies": base.lower()},
        )

        rates = {}
        for code, coin_id in ids.items():
            pair = f"{code}_{base}"

            try:
                value = data[coin_id][base.lower()]
            except (KeyError, TypeError):
                raise ApiRequestError(f"CoinGecko: нет курса {pair}") from None

            rates[pair] = self.validate_rate(value, pair)
        return rates


class ExchangeRateApiClient(BaseApiClient):

    def fetch_rates(self) -> dict:
        """Возвращает котировки из ExchangeRateApiClient."""
        key = self.config.EXCHANGE_RATE_API_KEY

        if not key:
            raise ApiRequestError("Не задан EXCHANGE_RATE_API_KEY")

        base = self.config.BASE_FIAT_CURRENCY
        url = f"{self.config.EXCHANGERATE_API_URL}/{key}/latest/{base}"
        data = self.get_json(url)

        if data.get("result") != "success":
            reason = data.get("error-type", "неизвестная ошибка")
            raise ApiRequestError(f"ExchangeRate-API: {reason}")

        conversions = data.get("conversion_rates")
        if not isinstance(conversions, dict):
            raise ApiRequestError("ExchangeRate-API: нет conversion_rates в ответе")

        rates = {}
        for code in self.config.FIAT_CURRENCIES:
            pair = f"{code}_{base}"
            value = self.validate_rate(conversions.get(code), f"{base}_{code}")
            rates[pair] = 1 / value

        return rates
