"""
Migración para añadir columnas reset_code_hash y reset_code_expires_at a la tabla profiles.
"""

from sqlalchemy import text
from database import SessionLocal

def migrate_password_reset_columns():
    db = SessionLocal()
    try:
        db.execute(text("""
            ALTER TABLE profiles 
            ADD COLUMN IF NOT EXISTS reset_code_hash TEXT,
            ADD COLUMN IF NOT EXISTS reset_code_expires_at TIMESTAMPTZ;
        """))
        db.commit()
        print("[OK] Columnas reset_code_hash y reset_code_expires_at anadidas correctamente a profiles.")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Error durante la migracion: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    migrate_password_reset_columns()
