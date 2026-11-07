import json
from datetime import UTC, datetime
from pathlib import Path

from valutatrade_hub.parser_service.config import ParserConfig


class RatesStorage:
    def __init__(self, config: ParserConfig):
        self.path = Path(config.RATES_FILE_PATH)
        self.history_path = Path(config.HISTORY_FILE_PATH)

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

        try:
            with self.history_path.open(encoding="utf-8") as file:
                history = json.load(file)

        except FileNotFoundError:
            history = []

        if not isinstance(history, list):
            raise TypeError("История курсов должна быть JSON-списком")

        known_ids = {record["id"] for record in history}
        for pair, quote in rates["pairs"].items():
            measured_at = datetime.fromisoformat(quote["updated_at"])

            if measured_at.tzinfo is None:
                raise ValueError(f"Не задан часовой пояс измерения {pair}")

            timestamp = measured_at.astimezone(UTC).isoformat()
            record_id = f"{pair}_{timestamp}"

            if record_id in known_ids:
                continue

            from_currency, to_currency = pair.split("_")

            history.append(
                {
                    "id": record_id,
                    "from_currency": from_currency,
                    "to_currency": to_currency,
                    "rate": quote["rate"],
                    "timestamp": timestamp,
                    "source": quote["source"],
                }
            )
            known_ids.add(record_id)

        self._write_json(self.history_path, history)
        self._write_json(self.path, merged)

        return merged

    @staticmethod
    def _write_json(path: Path, data: dict | list) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(path.name + ".tmp")

        try:
            with temporary_path.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)

            temporary_path.replace(path)
        finally:
            temporary_path.unlink(missing_ok=True)
