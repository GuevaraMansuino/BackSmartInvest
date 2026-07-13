"""
Script de inicialización y siembra de datos de desarrollo (Seed Dev).
Crea el usuario inicial gguevaraman@gmail.com con contraseña temporal hasheada para autenticación nativa.
"""

import uuid
from sqlalchemy import text
from database import engine
from security.password import hash_password


SEED_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
SEED_EMAIL = "gguevaraman@gmail.com"
SEED_PASSWORD = "SmartInvest2026!"


def seed_dev():
    password_hash = hash_password(SEED_PASSWORD)

    with engine.connect() as conn:
        with conn.begin():
            # 1. Ejecutar migración de campos si no existen
            try:
                conn.execute(text("""
                    ALTER TABLE public.profiles
                        ADD COLUMN IF NOT EXISTS password_hash TEXT NULL,
                        ADD COLUMN IF NOT EXISTS failed_login_attempts INTEGER NOT NULL DEFAULT 0,
                        ADD COLUMN IF NOT EXISTS locked_until TIMESTAMPTZ NULL,
                        ADD COLUMN IF NOT EXISTS refresh_token_hash TEXT NULL,
                        ADD COLUMN IF NOT EXISTS refresh_token_expires_at TIMESTAMPTZ NULL;
                """))
            except Exception as e:
                print("Nota: Verificación de schema en profiles:", e)

            # 2. Intentar crear en auth.users si existe y hay permisos
            try:
                conn.execute(text("""
                    INSERT INTO auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, created_at, updated_at)
                    VALUES (:id, 'authenticated', 'authenticated', :email, :hash, now(), now(), now())
                    ON CONFLICT (id) DO NOTHING;
                """), {"id": SEED_USER_ID, "email": SEED_EMAIL, "hash": password_hash})
            except Exception as e:
                print("Nota: No se pudo insertar en auth.users (puede gestionarse externamente):", e)

            # 3. Insertar o actualizar usuario seed en public.profiles
            try:
                conn.execute(text("""
                    INSERT INTO public.profiles (id, email, password_hash, failed_login_attempts, locked_until)
                    VALUES (:id, :email, :hash, 0, NULL)
                    ON CONFLICT (email) DO UPDATE SET
                        password_hash = EXCLUDED.password_hash,
                        failed_login_attempts = 0,
                        locked_until = NULL;
                """), {"id": SEED_USER_ID, "email": SEED_EMAIL, "hash": password_hash})
                print(f"Usuario seed creado/actualizado exitosamente: {SEED_EMAIL}")
            except Exception as e:
                print("Error insertando en public.profiles:", e)

            # 4. Asegurar cartera inicial asignada al usuario
            try:
                conn.execute(text("""
                    INSERT INTO public.portfolios (name, user_id)
                    VALUES ('Mi Billetera Principal', :id)
                    ON CONFLICT DO NOTHING;
                """), {"id": SEED_USER_ID})
            except Exception as e:
                print("Error insertando cartera en public.portfolios:", e)

    print(f"DB Seed completada. Usuario: {SEED_EMAIL} | Contraseña temporal: {SEED_PASSWORD}")


if __name__ == "__main__":
    seed_dev()
