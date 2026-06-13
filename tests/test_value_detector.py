from app.models.value_detector import calculate_edge


def test_calculate_edge_value_signal():
    result = calculate_edge(0.60, 2.0)
    assert result["implied_probability"] == 0.5
    assert result["edge"] == 0.09999999999999998
    assert result["expected_value"] == 0.19999999999999996
    assert result["signal"] == "value"


def test_calculate_edge_no_value_signal():
    result = calculate_edge(0.40, 2.0)
    assert result["signal"] == "no_value"

