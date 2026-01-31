from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from schemas.database_models import SessionModel, User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Хешируем пароль перед сохранением в БД"""
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Проверяем пароль при логине"""
    return pwd_context.verify(password, hashed)


# ---------------------------
# Users
# ---------------------------
async def create_user(db: AsyncSession, identifier: str, password_plain: str) -> User:
    user = User(
        identifier=identifier,
        metadata_={"password": hash_password(password_plain)},
        created=datetime.utcnow(),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_user_by_login(db: AsyncSession, identifier: str) -> Optional[User]:
    stmt = select(User).where(User.identifier == identifier)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    stmt = select(User).where(User.id == user_id)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


# ---------------------------
# Sessions
# ---------------------------
async def create_session(db: AsyncSession, user_id: UUID) -> str:
    token = base64.urlsafe_b64encode(os.urandom(24)).decode()
    expires = datetime.utcnow() + timedelta(days=30)

    session = SessionModel(
        token=token,
        user_id=user_id,
        created=datetime.utcnow(),
        expires=expires,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return token


async def get_session_by_token(db: AsyncSession, token: str) -> Optional[SessionModel]:
    if not token:
        return None
    if not isinstance(token, str):
        token = getattr(token, "value", None)
    if not token:
        return None

    stmt = select(SessionModel).where(SessionModel.token == token)
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if not session:
        return None

    if session.expires <= datetime.utcnow():
        await db.delete(session)
        await db.commit()
        return None

    return session


async def get_current_user(db: AsyncSession, session_token: str) -> Optional[User]:
    session = await get_session_by_token(db, session_token)
    if not session:
        return None
    user = await get_user_by_id(db, session.user_id)
    return user


async def destroy_session(db: AsyncSession, session_token: Optional[str]) -> None:
    if not session_token:
        return
    stmt = select(SessionModel).where(SessionModel.token == session_token)
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if session:
        await db.delete(session)
        await db.commit()
