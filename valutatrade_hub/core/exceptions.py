class CurrencyNotFoundError(ValueError):
    def __init__(self, code: str):
        super().__init__(f"Неизвестная валюта '{code}'")
