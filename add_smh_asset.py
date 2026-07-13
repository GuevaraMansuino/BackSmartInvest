"""
Script para insertar inmediatamente SMH y activos de semiconductores en la tabla assets.
"""

from database import SessionLocal
from services.asset_service import upsert_asset

NEW_ASSETS = [
    ("SMH", "VanEck Semiconductor ETF"),
    ("SOXX", "iShares Semiconductor ETF"),
    ("AMD", "Advanced Micro Devices Inc."),
    ("AVGO", "Broadcom Inc."),
    ("TSM", "Taiwan Semiconductor Manufacturing Co."),
]


def add_smh_and_semiconductors():
    db = SessionLocal()
    try:
        for symbol, name in NEW_ASSETS:
            asset = upsert_asset(db, symbol=symbol, name=name)
            print(f"[OK] Activo disponible: {asset.symbol} - {asset.name}")
    finally:
        db.close()


if __name__ == "__main__":
    add_smh_and_semiconductors()
