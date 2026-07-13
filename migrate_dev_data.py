"""
Script para migrar todos los datos de portafolios, transacciones y estrategias
desde el usuario anterior (00000000-0000-0000-0000-000000000000 / dev@smartinvest.com)
al nuevo usuario principal (11111111-1111-1111-1111-111111111111 / gguevaraman@gmail.com).
"""

from uuid import UUID
from sqlalchemy import select, update, delete
from database import SessionLocal
from models.entities import Profile, Portfolio, Transaction, Strategy


def migrate_dev_user_data():
    db = SessionLocal()
    try:
        OLD_USER_ID = UUID("00000000-0000-0000-0000-000000000000")
        NEW_USER_ID = UUID("11111111-1111-1111-1111-111111111111")

        old_portfolios = db.scalars(
            select(Portfolio).where(Portfolio.user_id == OLD_USER_ID)
        ).all()

        new_portfolios = db.scalars(
            select(Portfolio).where(Portfolio.user_id == NEW_USER_ID)
        ).all()

        new_portfolios_by_name = {p.name: p for p in new_portfolios}

        moved_txs = 0
        moved_strategies = 0
        migrated_portfolios = 0
        merged_portfolios = 0

        for old_p in old_portfolios:
            if old_p.name in new_portfolios_by_name:
                new_p = new_portfolios_by_name[old_p.name]

                # 1. Mover transacciones directamente en DB
                res_tx = db.execute(
                    update(Transaction)
                    .where(Transaction.portfolio_id == old_p.id)
                    .values(portfolio_id=new_p.id)
                )
                moved_txs += res_tx.rowcount or 0

                # 2. Mover estrategias que no colisionen en asset_id
                existing_asset_ids = {
                    s.asset_id
                    for s in db.scalars(
                        select(Strategy).where(Strategy.portfolio_id == new_p.id)
                    ).all()
                }
                old_strats = db.scalars(
                    select(Strategy).where(Strategy.portfolio_id == old_p.id)
                ).all()
                for st in old_strats:
                    if st.asset_id not in existing_asset_ids:
                        st.portfolio_id = new_p.id
                        existing_asset_ids.add(st.asset_id)
                        moved_strategies += 1
                    else:
                        db.delete(st)

                db.flush()
                # 3. Eliminar el portafolio antiguo una vez vaciado
                db.execute(
                    delete(Portfolio).where(Portfolio.id == old_p.id)
                )
                merged_portfolios += 1
            else:
                db.execute(
                    update(Portfolio)
                    .where(Portfolio.id == old_p.id)
                    .values(user_id=NEW_USER_ID)
                )
                migrated_portfolios += 1

        db.commit()
        print("Migracion completada con exito:")
        print(f"  - Portafolios transferidos directamente: {migrated_portfolios}")
        print(f"  - Portafolios fusionados por nombre duplicado: {merged_portfolios}")
        print(f"  - Transacciones reasignadas: {moved_txs}")
        print(f"  - Estrategias reasignadas: {moved_strategies}")

    except Exception as e:
        db.rollback()
        print(f"Error en migracion: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    migrate_dev_user_data()
