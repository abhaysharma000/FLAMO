"""Unit tests for the Calculator tool."""

import pytest
from app.tools.calculator import calculator


def test_calculator_basic_operations():
    assert calculator.invoke({"a": 125, "b": 48, "operation": "multiply"}) == 6000.0
    assert calculator.invoke({"a": 100, "b": 25, "operation": "add"}) == 125.0
    assert calculator.invoke({"a": 100, "b": 25, "operation": "subtract"}) == 75.0
    assert calculator.invoke({"a": 100, "b": 25, "operation": "divide"}) == 4.0
    assert calculator.invoke({"a": 2, "b": 8, "operation": "power"}) == 256.0
    assert calculator.invoke({"a": 17, "b": 5, "operation": "modulo"}) == 2.0


def test_calculator_division_by_zero():
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        calculator.invoke({"a": 100, "b": 0, "operation": "divide"})


def test_calculator_expression_evaluation():
    assert calculator.invoke({"expression": "125 * 48"}) == 6000.0
    assert calculator.invoke({"expression": "(125 * 48) / 5"}) == 1200.0
    assert calculator.invoke({"expression": "10 + 20 * 3"}) == 70.0


def test_calculator_expression_zero_division():
    with pytest.raises(ValueError, match="Cannot divide by zero"):
        calculator.invoke({"expression": "100 / 0"})


def test_calculator_invalid_operation():
    with pytest.raises(ValueError, match="Invalid operation"):
        calculator.invoke({"a": 10, "b": 5, "operation": "integrate"})
