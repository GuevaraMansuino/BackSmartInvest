from decimal import Decimal


def calculate_rebalance_difference(
    total_portfolio_value: Decimal | float | int,
    target_asset_percentage: Decimal | float | int,
    current_asset_value: Decimal | float | int,
) -> Decimal:
    total_value = Decimal(str(total_portfolio_value))
    target_percentage = Decimal(str(target_asset_percentage))
    current_value = Decimal(str(current_asset_value))

    return (total_value * target_percentage / Decimal("100")) - current_value
