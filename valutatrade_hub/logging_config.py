import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


def get_logger(name: str = "actions") -> logging.Logger:
    logger = logging.getLogger(f"valutatrade.{name}")

    if not logger.handlers:
        settings = SettingsLoader()

        logs_dir = Path(settings.get("logs_dir"))
        logs_dir.mkdir(parents=True, exist_ok=True)

        handler = RotatingFileHandler(
            logs_dir / f"{name}.log",
            maxBytes=1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )

        handler.setFormatter(
            logging.Formatter(settings.get("log_format"), datefmt="%Y-%m-%dT%H:%M:%S")
        )

        logger.addHandler(handler)
        logger.setLevel(settings.get("log_level", "INFO"))
        logger.propagate = False
    return logger
