import math
from datetime import datetime

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.logging_config import get_logger
from valutatrade_hub.parser_service.api_clients import BaseApiClient
from valutatrade_hub.parser_service.config import ParserConfig
from valutatrade_hub.parser_service.storage import RatesStorage


class RatesUpdater:
    def __init__(
        self,
        api_config: ParserConfig,
        clients: list[BaseApiClient],
        storage: RatesStorage,
    ):
        self.api_config = api_config
        self.clients = clients
        self.storage = storage
        self.logger = get_logger("parser")

    def run_update(self) -> dict:
        self.logger.info("Начало обновления курсов")
        quotes = {}
        sources = []
        errors = []

        for client in self.clients:
            name = type(client).__name__

            self.logger.info("Запрос курсов: %s", name)

            try:
                fetched = client.fetch_rates()

                if not fetched:
                    raise ApiRequestError("Источник вернул пустой список курсов")

            except ApiRequestError as error:
                self.logger.error("Ошибка %s: %s", name, error)
                errors.append(name)
                continue

            quotes.update(fetched)
            sources.append(name)

            self.logger.info("%s: получено курсов — %s", name, len(fetched))

        if not quotes:
            self.logger.error("Обновление данных отменено: ни один источник не ответил")
            raise ApiRequestError("Не удалось получить курсы ни от одного источника")

        base = self.api_config.BASE_FIAT_CURRENCY
        values = {base: 1.0}

        for pair, value in quotes.items():

            code, quote_base = pair.split("_")

            if quote_base != base:
                raise ApiRequestError(f"Неожиданная базовая валюта в паре {pair}")

            values[code] = value

        rates = {}
        for source, source_value in values.items():
            rates[source] = {}

            for target, target_value in values.items():
                if source == target:
                    continue

                rate = source_value / target_value

                if not math.isfinite(rate) or rate <= 0:
                    raise ApiRequestError(f"Некорректный курс {source}->{target}")

                rates[source][target] = rate

        rates["source"] = ", ".join(sources)
        rates["last_refresh"] = datetime.now().astimezone().isoformat()

        self.logger.info("Сохранение %s полученных курсов", len(quotes))

        try:
            self.storage.save_rates(rates)
        except (OSError, ValueError) as error:
            self.logger.error("Не удалось сохранить курсы: %s", error)
            raise

        self.logger.info(
            "Обновление завершено: курсов — %s, ошибок источников — %s",
            len(quotes),
            len(errors),
        )

        return {
            "rates": rates,
            "updated_count": len(quotes),
            "last_refresh": rates["last_refresh"],
            "errors": errors,
        }
