"""
Script para insertar los CEDEARs XLY, XLI, XLP, XLV y sectores SPDR en la base de datos.
"""
from database import SessionLocal
from services.asset_service import upsert_asset

SECTOR_CEDEARS = [
    ("XLY", "Consumer Discretionary Select Sector SPDR Fund"),
    ("XLI", "Industrial Select Sector SPDR Fund"),
    ("XLP", "Consumer Staples Select Sector SPDR Fund"),
    ("XLV", "Health Care Select Sector SPDR Fund"),
    ("XLE", "Energy Select Sector SPDR Fund"),
    ("XLF", "Financial Select Sector SPDR Fund"),
    ("XLK", "Technology Select Sector SPDR Fund"),
    ("XLC", "Communication Services Select Sector SPDR Fund"),
    ("XLU", "Utilities Select Sector SPDR Fund"),
    ("XLB", "Materials Select Sector SPDR Fund"),
    ("XLRE", "Real Estate Select Sector SPDR Fund"),
]

def add_cedears():
    db = SessionLocal()
    try:
        for symbol, name in SECTOR_CEDEARS:
            asset = upsert_asset(db, symbol=symbol, name=name)
            print(f"[OK] Activo disponible: {asset.symbol} - {asset.name} (ID: {asset.id})")
    finally:
        db.close()

if __name__ == "__main__":
    add_cedears()
