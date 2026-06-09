"""
Unit tests para services.rebalance_logic.calculate_rebalance_difference

Verifica cálculo: (total * target_pct / 100) - current_value
"""

from decimal import Decimal

import pytest

from services.rebalance_logic import calculate_rebalance_difference


class TestCalculateRebalanceDifference:
    def test_needs_to_buy(self):
        # Total=$1000, target=50%, current=$400 → diferencia=$100 (comprar)
        result = calculate_rebalance_difference(1000, 50, 400)
        assert result == Decimal("100")

    def test_needs_to_sell(self):
        # Total=$1000, target=20%, current=$300 → diferencia=-$100 (vender)
        result = calculate_rebalance_difference(1000, 20, 300)
        assert result == Decimal("-100")

    def test_perfectly_balanced(self):
        result = calculate_rebalance_difference(1000, 50, 500)
        assert result == Decimal("0")

    def test_zero_current_value(self):
        # Activo nuevo, nada comprado
        result = calculate_rebalance_difference(2000, 25, 0)
        assert result == Decimal("500")

    def test_zero_total(self):
        # Portfolio vacío → diferencia cero (no hay nada que rebalancear)
        result = calculate_rebalance_difference(0, 50, 0)
        assert result == Decimal("0")

    def test_decimal_precision(self):
        result = calculate_rebalance_difference(Decimal("1500.50"), Decimal("33.33"), Decimal("499.00"))
        expected = (Decimal("1500.50") * Decimal("33.33") / Decimal("100")) - Decimal("499.00")
        assert result == expected

    def test_accepts_floats(self):
        result = calculate_rebalance_difference(1000.0, 30.5, 200.0)
        assert result == Decimal("105")

    def test_full_portfolio_rebalance(self):
        # Simular un portfolio completo con 3 activos
        total = Decimal("10000")
        scenarios = [
            (40, 3800),  # target=$4000, actual=$3800 → +200 (comprar)
            (40, 5000),  # target=$4000, actual=$5000 → -1000 (vender)
            (20, 3200),  # target=$2000, actual=$3200 → -1200 (vender)
        ]
        results = [
            calculate_rebalance_difference(total, pct, current)
            for pct, current in scenarios
        ]
        assert results[0] == Decimal("200")
        assert results[1] == Decimal("-1000")
        assert results[2] == Decimal("-1200")
