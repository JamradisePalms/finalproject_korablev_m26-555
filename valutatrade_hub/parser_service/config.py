import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

from valutatrade_hub.infra.settings import SettingsLoader

load_dotenv()


settings = SettingsLoader()


@dataclass
class ParserConfig:
    EXCHANGE_RATE_API_KEY: str | None = field(
        default_factory=lambda: os.getenv("EXCHANGE_RATE_API_KEY"), repr=False
    )

    COINGECKO_URL: str = "https://api.coingecko.com/api/v3/simple/price"
    EXCHANGERATE_API_URL: str = "https://v6.exchangerate-api.com/v6"

    BASE_FIAT_CURRENCY: str = "USD"
    FIAT_CURRENCIES: tuple[str, ...] = ("EUR", "GBP", "RUB")
    CRYPTO_CURRENCIES: tuple[str, ...] = ("BTC", "ETH", "SOL")

    CRYPTO_ID_MAP: dict[str, str] = field(
        default_factory=lambda: {
            "BTC": "bitcoin",
            "ETH": "ethereum",
            "SOL": "solana",
        }
    )

    REQUEST_TIMEOUT: int = 10
    RATES_FILE_PATH: str = f"{settings.get('data_dir', 'data')}/rates.json"
    HISTORY_FILE_PATH: str = f"{settings.get('data_dir', 'data')}/exchange_rates.json"
