import json
from datetime import UTC, datetime
from pathlib import Path

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.core.utils import validate_quote
from valutatrade_hub.infra.database import write_json
from valutatrade_hub.logging_config import get_logger
from valutatrade_hub.parser_service.config import ParserConfig


class RatesStorage:
    def __init__(self, config: ParserConfig):
        self.path = Path(config.RATES_FILE_PATH)
        self.history_path = Path(config.HISTORY_FILE_PATH)

    def load_rates(self) -> dict:
        try:
            with self.path.open(encoding="utf-8") as file:
                rates = json.load(file)

            if not isinstance(rates, dict) or not isinstance(rates.get("pairs"), dict):
                raise TypeError("Ожидается словарь pairs")

            last_refresh = rates.get("last_refresh")
            if (
                last_refresh is not None
                and datetime.fromisoformat(last_refresh).tzinfo is None
            ):
                raise ValueError("В last_refresh не задан часовой пояс")

            for pair, quote in rates["pairs"].items():
                from_code, to_code = pair.split("_")
                validate_quote(quote, from_code, to_code)

        except FileNotFoundError:
            return {"pairs": {}}
        except (ApiRequestError, TypeError, ValueError, OverflowError) as error:
            get_logger("parser").warning("Кеш курсов повреждён: %s", error)
            return {"pairs": {}}

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

        write_json(self.history_path, history)
        write_json(self.path, merged)

        return merged
