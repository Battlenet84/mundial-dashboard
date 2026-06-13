import pytest

from app.models.implied_probability import decimal_to_implied_probability


def test_decimal_to_implied_probability():
    assert decimal_to_implied_probability(2.0) == 0.5


def test_decimal_to_implied_probability_rejects_invalid_odds():
    with pytest.raises(ValueError):
        decimal_to_implied_probability(1.0)

