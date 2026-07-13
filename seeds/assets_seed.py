"""
Seed script para poblar la tabla assets con instrumentos comunes.

Uso:
    cd backend
    python -m seeds.assets_seed

Requiere que la base de datos esté configurada en .env
"""

import sys
from pathlib import Path

# Asegurar que el directorio raíz del backend esté en el path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from services.asset_service import upsert_asset

INITIAL_ASSETS: list[tuple[str, str]] = [
    # ETFs globales
    ("SPY", "SPDR S&P 500 ETF Trust"),
    ("QQQ", "Invesco QQQ Trust (Nasdaq-100 ETF)"),
    ("VTI", "Vanguard Total Stock Market ETF"),
    ("VOO", "Vanguard S&P 500 ETF"),
    ("ARKK", "ARK Innovation ETF"),
    ("EEM", "iShares MSCI Emerging Markets ETF"),
    ("GLD", "SPDR Gold Trust ETF"),
    ("TLT", "iShares 20+ Year Treasury Bond ETF"),
    ("SMH", "VanEck Semiconductor ETF"),
    ("SOXX", "iShares Semiconductor ETF"),
    # Acciones globales
    ("AAPL", "Apple Inc."),
    ("AMD", "Advanced Micro Devices Inc."),
    ("AVGO", "Broadcom Inc."),
    ("TSM", "Taiwan Semiconductor Manufacturing Co."),
    ("MSFT", "Microsoft Corporation"),
    ("GOOGL", "Alphabet Inc. (Class A)"),
    ("AMZN", "Amazon.com Inc."),
    ("NVDA", "NVIDIA Corporation"),
    ("TSLA", "Tesla Inc."),
    ("META", "Meta Platforms Inc."),
    ("BRK.B", "Berkshire Hathaway Inc. (Class B)"),
    ("JPM", "JPMorgan Chase & Co."),
    ("V", "Visa Inc."),
    # Activos argentinos (cedears principales)
    ("GGAL", "Grupo Financiero Galicia S.A."),
    ("YPF", "YPF S.A."),
    ("MELI", "MercadoLibre Inc."),
    ("GLOB", "Globant S.A."),
    ("PAM", "Pampa Energía S.A."),
    ("SUPV", "Grupo Supervielle S.A."),
    # Criptomonedas
    ("BTC", "Bitcoin"),
    ("ETH", "Ethereum"),
    ("SOL", "Solana"),
    ("USDC", "USD Coin (stablecoin)"),
    ("USDT", "Tether (stablecoin)"),
    # Bonos y renta fija (referencia)
    ("AY24", "Bono Global Argentina 2024 (USD)"),
    ("GD30", "Bono Global Argentina 2030 (USD)"),
]


def run_seed() -> None:
    db = SessionLocal()
    created = 0
    skipped = 0

    try:
        for symbol, name in INITIAL_ASSETS:
            asset = upsert_asset(db, symbol=symbol, name=name)
            if asset.name == name:
                created += 1
            else:
                skipped += 1
            print(f"  {'✓' if asset else '?'} {asset.symbol} — {asset.name}")
    finally:
        db.close()

    print(f"\nSeed completado: {created} insertados, {skipped} ya existían.")


if __name__ == "__main__":
    print("🌱 Iniciando seed de activos...\n")
    run_seed()
