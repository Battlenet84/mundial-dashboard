from app.models.implied_probability import decimal_to_implied_probability


def calculate_edge(model_probability: float, decimal_odds: float) -> dict:
    implied_probability = decimal_to_implied_probability(decimal_odds)
    edge = model_probability - implied_probability
    expected_value = model_probability * decimal_odds - 1
    return {
        "model_probability": model_probability,
        "decimal_odds": decimal_odds,
        "implied_probability": implied_probability,
        "edge": edge,
        "expected_value": expected_value,
        "signal": "value" if expected_value > 0 else "no_value",
    }

