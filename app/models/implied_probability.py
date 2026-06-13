def decimal_to_implied_probability(decimal_odds: float) -> float:
    if decimal_odds <= 1:
        raise ValueError("Decimal odds must be greater than 1")
    return 1 / decimal_odds

