import tomllib
from typing import Any


class SettingsLoader:
    """Singleton через __new__: проще и понятнее метакласса."""

    instance = None

    def __new__(cls):
        if cls.instance is None:
            cls.instance = super().__new__(cls)
        return cls.instance

    def __init__(self):
        if hasattr(self, "_settings"):
            return

        with open("pyproject.toml", "rb") as file:
            config = tomllib.load(file)

        self._settings = {
            "data_dir": "data",
            "logs_dir": "logs",
            "rates_ttl_seconds": 300,
            "base_currency": "USD",
            "log_format": "%(levelname)s %(asctime)s %(message)s",
        }
        self._settings.update(config.get("tool", {}).get("valutatrade", {}))

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)
