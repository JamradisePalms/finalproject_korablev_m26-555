import json
import math
from pathlib import Path

from valutatrade_hub.core.currencies import get_currency
from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.models import CURRENCIES
from valutatrade_hub.infra.settings import SettingsLoader


def get_mock_rates() -> dict:
    rates = {}
    for source, source_value in CURRENCIES.items():
        rates[source] = {}
        for target, target_value in CURRENCIES.items():
            if source != target:
                rates[source][target] = source_value / target_value
    rates["source"] = "Mock"
    return rates


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


def get_pair_rate(rates: dict, from_code: str, to_code: str) -> float:
    get_currency(from_code)
    get_currency(to_code)

    source = rates.get(from_code)

    if not isinstance(source, dict):
        raise ApiRequestError(f"Нет курсов для {from_code}")

    rate = 1.0 if from_code == to_code else source.get(to_code)

    if (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or rate <= 0
    ):
        raise ApiRequestError(f"Курс {from_code}->{to_code} недоступен")

    return float(rate)
