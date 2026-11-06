import json
from datetime import datetime
from pathlib import Path

from valutatrade_hub.parser_service.config import ParserConfig


class RatesStorage:
    def __init__(self, config: ParserConfig):
        self.path = Path(config.RATES_FILE_PATH)

    def load_rates(self) -> dict:
        try:
            with self.path.open(encoding="utf-8") as file:
                rates = json.load(file)
        except FileNotFoundError:
            return {"pairs": {}}

        if not isinstance(rates, dict) or not isinstance(rates.get("pairs"), dict):
            raise TypeError("Некорректный формат кеша: ожидается словарь pairs")

        return rates

    def save_rates(self, rates: dict) -> dict:
        cached = self.load_rates()

        pairs = cached["pairs"].copy()
        for pair, quote in rates["pairs"].items():
            previous = pairs.get(pair)


            if previous is None or datetime.fromisoformat(
                quote["updated_at"]
            ) > datetime.fromisoformat(previous["updated_at"]):
                pairs[pair] = quote

        merged = {
            "base_currency": rates["base_currency"],
            "last_refresh": max(
                filter(None, [cached.get("last_refresh"), rates["last_refresh"]]),
                key=datetime.fromisoformat,
            ),
            "pairs": pairs,
        }

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(self.path.name + ".tmp")

        try:
            with temporary_path.open("w", encoding="utf-8") as file:
                json.dump(merged, file, ensure_ascii=False, indent=2, allow_nan=False)
            temporary_path.replace(self.path)
        finally:
            temporary_path.unlink(missing_ok=True)

        return merged
