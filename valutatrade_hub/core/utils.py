from valutatrade_hub.core.models import CURRENCIES


def get_mock_rates() -> dict:
    rates = {}
    for source, source_value in CURRENCIES.items():
        rates[source] = {}
        for target, target_value in CURRENCIES.items():
            if source != target:
                rates[source][target] = source_value / target_value
    rates["source"] = "Mock"
    return rates
