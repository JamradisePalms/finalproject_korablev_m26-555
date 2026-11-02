import argparse
import shlex

from valutatrade_hub.core.usecases import (
    buy,
    deposit,
    get_rate,
    login,
    register,
    sell,
    show_portfolio,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="", description="Валютный кошелёк")
    commands = parser.add_subparsers(dest="command", required=True)

    for name in ("register", "login"):
        command = commands.add_parser(name)
        command.add_argument("--username", required=True)
        command.add_argument("--password", required=True)

    command = commands.add_parser("show-portfolio")

    command.add_argument("--base", default="USD")

    for name in ("buy", "sell"):
        command = commands.add_parser(name)
        command.add_argument("--currency", required=True)
        command.add_argument("--amount", type=float, required=True)

    command = commands.add_parser("deposit")
    command.add_argument("--amount", type=float, required=True)

    command = commands.add_parser("get-rate")

    command.add_argument("--from", dest="from_currency", required=True)
    command.add_argument("--to", dest="to_currency", required=True)

    commands.add_parser("help")
    commands.add_parser("exit")

    return parser


def main() -> None:
    parser = _parser()

    current_user_id = None

    print("Валютный кошелёк. Введите help для списка команд, exit для выхода.")

    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line.strip():
            continue

        try:
            args = parser.parse_args(shlex.split(line))

            if args.command == "exit":
                break

            if args.command == "help":
                parser.print_help()
            elif args.command == "register":
                register(args.username, args.password)
            elif args.command == "login":
                current_user_id = login(args.username, args.password)
            elif args.command == "show-portfolio":
                show_portfolio(current_user_id, args.base)
            elif args.command == "buy":
                buy(current_user_id, args.currency, args.amount)
            elif args.command == "sell":
                sell(current_user_id, args.currency, args.amount)
            elif args.command == "deposit":
                deposit(current_user_id, args.amount)
            elif args.command == "get-rate":
                get_rate(args.from_currency, args.to_currency)
        except SystemExit:
            continue
        except (ValueError, TypeError, OSError, KeyError) as error:
            print(f"Ошибка: {error}")
