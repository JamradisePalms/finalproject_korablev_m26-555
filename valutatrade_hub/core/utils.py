import json
import math
from datetime import UTC, datetime
from pathlib import Path

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.models import CURRENCIES
from valutatrade_hub.infra.settings import SettingsLoader


def get_mock_rates() -> dict:
    timestamp = datetime.now(UTC).isoformat()
    return {
        "base_currency": "USD",
        "last_refresh": timestamp,
        "pairs": {
            f"{code}_USD": {
                "rate": value / CURRENCIES["USD"],
                "updated_at": timestamp,
                "source": "Mock",
            }
            for code, value in CURRENCIES.items()
            if code != "USD"
        },
    }


def load_json(filename: str):
    data_dir = SettingsLoader().get("data_dir")
    with open(f"{data_dir}/{filename}", encoding="utf-8") as file:
        return json.load(file)


def save_json(filename: str, records: list[dict] | dict) -> None:
    data_dir = SettingsLoader().get("data_dir")
    path = Path(data_dir) / filename
    temporary_path = path.with_name(path.name + ".tmp")

    try:
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(records, file, ensure_ascii=False, indent=2, allow_nan=False)
        temporary_path.replace(path)

    finally:
        temporary_path.unlink(missing_ok=True)


def validate_amount(amount: float) -> None:
    if (
        isinstance(amount, bool)
        or not isinstance(amount, (int, float))
        or not math.isfinite(amount)
        or amount <= 0
    ):
        raise ValueError("Сумма должна быть конечным положительным числом")


def get_pair_quote(rates: dict, from_code: str, to_code: str) -> dict:
    if from_code == to_code:
        return {
            "rate": 1.0,
            "updated_at": datetime.now(UTC).isoformat(),
            "source": "Identity",
        }

    if not isinstance(rates, dict) or not isinstance(rates.get("pairs"), dict):
        raise ApiRequestError("Некорректный формат кеша. Выполните update-rates")

    pairs = rates["pairs"]
    direct = pairs.get(f"{from_code}_{to_code}")
    reverse = pairs.get(f"{to_code}_{from_code}")
    if direct is not None:
        if not isinstance(direct, dict):
            raise ApiRequestError(f"Некорректная котировка {from_code}->{to_code}")

        quote = dict(direct)
    elif reverse is not None:
        original = get_pair_quote(rates, to_code, from_code)

        quote = {**original, "rate": 1 / original["rate"]}
    else:
        base = rates.get("base_currency", "USD")

        if from_code == base or to_code == base:
            raise ApiRequestError(f"Курс {from_code}->{to_code} недоступен")

        source = get_pair_quote(rates, from_code, base)
        target = get_pair_quote(rates, to_code, base)

        quote = {
            "rate": source["rate"] / target["rate"],
            "updated_at": min(
                datetime.fromisoformat(source["updated_at"]),
                datetime.fromisoformat(target["updated_at"]),
            ).isoformat(),
            "source": ", ".join(dict.fromkeys([source["source"], target["source"]])),
        }

    rate = quote.get("rate")

    if (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or rate <= 0
    ):
        raise ApiRequestError(f"Курс {from_code}->{to_code} недоступен")
    try:
        timestamp = datetime.fromisoformat(quote["updated_at"])

        if timestamp.tzinfo is None:
            raise ValueError("Нет часового пояса")
    except (KeyError, TypeError, ValueError):
        raise ApiRequestError(f"Не задано время курса {from_code}->{to_code}") from None

    if not isinstance(quote.get("source"), str) or not quote["source"]:
        raise ApiRequestError(f"Не задан источник курса {from_code}->{to_code}")

    return {
        "rate": float(rate),
        "updated_at": timestamp.isoformat(),
        "source": quote["source"],
    }


def is_rate_stale(quote: dict) -> bool:
    ttl = SettingsLoader().get("rates_ttl_seconds")

    updated_at = datetime.fromisoformat(quote["updated_at"])

    age = (datetime.now(UTC) - updated_at).total_seconds()

    return not 0 <= age < ttl


def get_pair_rate(rates: dict, from_code: str, to_code: str) -> float:
    get_currency(from_code)
    get_currency(to_code)

    return get_pair_quote(rates, from_code, to_code)["rate"]
