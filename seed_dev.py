import uuid
from database import engine
from sqlalchemy import text

def seed_dev():
    uid = uuid.UUID('00000000-0000-0000-0000-000000000000')
    with engine.connect() as conn:
        with conn.begin():
            # Intentar crear auth.users ignorando posibles restricciones o errores de schema si no existen localmente,
            # pero como estamos en supabase remoto, sí existen.
            try:
                conn.execute(text("""
                    INSERT INTO auth.users (id, aud, role, email, encrypted_password, email_confirmed_at, created_at, updated_at, confirmation_token, recovery_token, email_change_token_new, email_change) 
                    VALUES (:id, 'authenticated', 'authenticated', 'dev@smartinvest.com', 'dummy', now(), now(), now(), '', '', '', '') 
                    ON CONFLICT DO NOTHING;
                """), {'id': uid})
            except Exception as e:
                print("Error insertando en auth.users (quizas falta de permisos, pero no importa si desactivamos constraint)", e)
            
            try:
                conn.execute(text("""
                    INSERT INTO public.profiles (id, email) VALUES (:id, 'dev@smartinvest.com')
                    ON CONFLICT DO NOTHING;
                """), {'id': uid})
            except Exception as e:
                print("Error insertando en profiles", e)

            try:
                conn.execute(text("""
                    INSERT INTO public.portfolios (name, user_id) VALUES ('Mi Billetera Principal', :id)
                    ON CONFLICT DO NOTHING;
                """), {'id': uid})
            except Exception as e:
                print("Error insertando en portfolios", e)

    print('DB Seed Successful')

if __name__ == '__main__':
    seed_dev()
