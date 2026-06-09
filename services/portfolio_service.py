from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dependencies.auth import AuthenticatedUser
from models import Portfolio, Profile
from schemas.portfolio import PortfolioCreate, PortfolioUpdate


def ensure_profile_exists(db: Session, current_user: AuthenticatedUser) -> Profile:
    profile = db.get(Profile, current_user.user_id)
    profile_email = current_user.email

    if not profile_email:
        raise ValueError("Authenticated user email is missing.")

    if profile is None:
        profile = Profile(
            id=current_user.user_id,
            email=profile_email,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile

    if profile_email and profile.email != profile_email:
        profile.email = profile_email
        db.commit()
        db.refresh(profile)

    return profile


def list_portfolios(db: Session, current_user: AuthenticatedUser) -> list[Portfolio]:
    ensure_profile_exists(db, current_user)
    statement = (
        select(Portfolio)
        .where(Portfolio.user_id == current_user.user_id)
        .order_by(Portfolio.created_at.desc())
    )
    return list(db.scalars(statement).all())


def get_portfolio_or_none(
    db: Session,
    current_user: AuthenticatedUser,
    portfolio_id: UUID,
) -> Portfolio | None:
    statement = select(Portfolio).where(
        Portfolio.id == portfolio_id,
        Portfolio.user_id == current_user.user_id,
    )
    return db.scalars(statement).one_or_none()


def create_portfolio(
    db: Session,
    current_user: AuthenticatedUser,
    payload: PortfolioCreate,
) -> Portfolio:
    ensure_profile_exists(db, current_user)
    portfolio = Portfolio(
        user_id=current_user.user_id,
        name=payload.name.strip(),
    )
    db.add(portfolio)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Portfolio name already exists for this user.") from exc

    db.refresh(portfolio)
    return portfolio


def update_portfolio(
    db: Session,
    portfolio: Portfolio,
    payload: PortfolioUpdate,
) -> Portfolio:
    portfolio.name = payload.name.strip()

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("Portfolio name already exists for this user.") from exc

    db.refresh(portfolio)
    return portfolio


def delete_portfolio(db: Session, portfolio: Portfolio) -> None:
    db.delete(portfolio)
    db.commit()
