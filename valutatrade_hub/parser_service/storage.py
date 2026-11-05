import json
from pathlib import Path

from valutatrade_hub.parser_service.config import ParserConfig


class RatesStorage:
    def __init__(self, config: ParserConfig):
        self.path = Path(config.RATES_FILE_PATH)

    def save_rates(self, rates: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_name(self.path.name + ".tmp")

        try:
            with temporary_path.open("w", encoding="utf-8") as file:
                json.dump(rates, file, ensure_ascii=False, indent=2, allow_nan=False)
            temporary_path.replace(self.path)
        finally:
            temporary_path.unlink(missing_ok=True)
