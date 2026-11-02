# Валютный кошелёк

Запуск из корня репозитория:

```bash
uv run finalproject-korablev-m26-555
```

Или `uv run main.py`.

Примеры команд внутри приложения:

```text
register --username alice --password 1234
login --username alice --password 1234
deposit --amount 1000
show-portfolio --base USD
buy --currency BTC --amount 0.05
sell --currency BTC --amount 0.01
get-rate --from USD --to BTC
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
