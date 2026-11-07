# Валютный кошелёк

ValutaTrade Hub — консольная симуляция торговли фиатными валютами и криптовалютами.
Пользователи и кошельки хранятся в JSON, котировки загружаются из CoinGecko
и ExchangeRate-API. Реальных платежей приложение не выполняет.

## Установка

Нужны Python 3.12 или новее и [uv](https://docs.astral.sh/uv/getting-started/installation/).
На macOS uv можно установить через `brew install uv`.
После клонирования репозитория перейдите в его корень и установите зависимости:

```bash
cd finalproject_korablev_m26-555
uv sync --locked
```

Создайте `.env` в корне проекта и укажите свой ключ из личного кабинета
[ExchangeRate-API](https://www.exchangerate-api.com/):

```dotenv
EXCHANGE_RATE_API_KEY=ваш_ключ
```

`.env` исключён из Git. Вместо файла можно задать переменную окружения
`EXCHANGE_RATE_API_KEY`. Для используемого запроса CoinGecko ключ не задан;
при ограничении сервиса приложение выводит ошибку API. Без ключа ExchangeRate
фиатный источник не обновляется, а доступные криптокотировки сохраняются.

## Структура

```text
valutatrade_hub/
  core/             модели, валюты, исключения и операции
  infra/            загрузка настроек
  parser_service/   API-клиенты, обновление и хранение котировок
  cli/              разбор и выполнение команд
  logging_config.py настройка логов
  decorators.py     логирование сделок
data/
  users.json          пользователи
  portfolios.json     кошельки и балансы
  rates.json          последние котировки
  exchange_rates.json история измерений
```

## Запуск и команды

Запуск из корня репозитория:

```bash
uv run finalproject-korablev-m26-555
```

Или `uv run main.py`.

Примеры команд внутри приложения:

```text
register --username demo_user --password demo1234
login --username demo_user --password demo1234
deposit --amount 1000
show-portfolio --base USD
buy --currency BTC --amount 0.05
sell --currency BTC --amount 0.01
get-rate --from USD --to BTC
update-rates
update-rates --source coingecko
show-rates
show-rates --currency RUB
show-rates --top 2 --base EUR
help
buy --help
exit
```

Значения с пробелами заключайте в кавычки. Покупка требует достаточного
USD-баланса. Курсы берутся из локального `data/rates.json`.

Ошибки команд:

- `buy`, `sell`: при нехватке средств выводятся доступная и требуемая суммы.
- `get-rate`: при неизвестной валюте предлагается `get-rate --help`.
- При сбое получения курсов предлагается повторить запрос позже или проверить сеть.
- Для `show-portfolio`, `buy`, `sell` и `deposit` сначала нужен успешный `login`.

Настройки находятся в секции `[tool.valutatrade]` файла `pyproject.toml`:
путь к данным, TTL курсов в секундах, базовая валюта показа, путь и формат логов.
Они читаются один раз при первом обращении к `SettingsLoader`.
После изменения настроек перезапустите приложение.

Логи покупок и продаж записываются в `logs/actions.log` в текстовом формате.
Ротация: размер файла до 1 МБ, три резервных файла с логами. По умолчанию уровень `INFO`;
`logs_dir`, `log_level` и `log_format` задаются в `[tool.valutatrade]`.
`@log_action(verbose=True)` добавляет баланс до и после операции.
Ошибка записывается в лог и передаётся дальше в CLI.

`update-rates` получает курсы от обоих API. Флаг `--source` выбирает один источник;
в этом случае обновляются только его пары, остальные котировки сохраняются.
При частичном отказе обновляются доступные котировки, остальные сохраняют прежнее время;
выводится предупреждение.
Если все выбранные источники недоступны, прежний файл остаётся без изменений.
Подробности обновления записываются в `logs/parser.log`.

`show-rates` читает локальный кеш без обращения к API. `--currency` фильтрует валюту,
`--top` выбирает самые дорогие криптовалюты, `--base` задаёт валюту отображения.
Для обеих команд вход в аккаунт не требуется.

Перед покупкой и продажей проверяется TTL используемой котировки. Если курс устарел,
сделка отклоняется без изменения балансов; сначала выполните `update-rates`.

`data/exchange_rates.json` хранит историю исходных измерений: `id`, `from_currency`,
`to_currency`, `rate`, `timestamp` (UTC), `source`.

Кеш содержит `base_currency`, `last_refresh` и словарь `pairs`; у каждой котировки
есть `rate`, `updated_at` и `source`.
