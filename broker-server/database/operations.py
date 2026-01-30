from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import Cookie
from passlib.context import CryptContext
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import async_session_factory
from schemas.database_models import SessionModel, User

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY", "change_me")


# ---------------------------
# DB session helper
# ---------------------------
async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


# ---------------------------
# Sessions (cookie auth)
# ---------------------------
async def create_session_db(
    db: AsyncSession, user_id: UUID, token: str, expires: datetime
) -> SessionModel:
    session = SessionModel(
        token=token,
        user_id=user_id,
        created=datetime.utcnow(),
        expires=expires,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_session_by_token(db: AsyncSession, token: str) -> Optional[SessionModel]:
    stmt = select(SessionModel).where(SessionModel.token == token)
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if not session:
        return None
    if session.expires <= datetime.utcnow():
        # expired -> delete
        await db.delete(session)
        await db.commit()
        return None
    return session


async def delete_session_db(db: AsyncSession, token: str) -> bool:
    stmt = select(SessionModel).where(SessionModel.token == token)
    res = await db.execute(stmt)
    session = res.scalar_one_or_none()
    if not session:
        return False
    await db.delete(session)
    await db.commit()
    return True


async def create_session(db: AsyncSession, user_id: UUID) -> str:
    token = base64.urlsafe_b64encode(os.urandom(24)).decode()
    expires = datetime.utcnow() + timedelta(days=30)
    await create_session_db(db=db, user_id=user_id, token=token, expires=expires)
    return token


async def destroy_session(db: AsyncSession, session_token: Optional[str]) -> None:
    if session_token:
        await delete_session_db(db, session_token)


async def get_current_user(
    session_token: Optional[str] = Cookie(None),
    db: AsyncSession = None,
) -> Optional[User]:
    if not session_token or db is None:
        return None
    session = await get_session_by_token(db, session_token)
    if not session:
        return None
    return await get_user_by_id(db, session.user_id)


# ---------------------------
# Users
# ---------------------------
async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    return await db.get(User, user_id)


async def get_user_by_login(db: AsyncSession, login: str) -> Optional[User]:
    stmt = select(User).where(User.identifier == login)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def list_users(db: AsyncSession) -> list[User]:
    stmt = select(User).order_by(User.createdAt.is_(None), User.createdAt)
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def create_user(
    db: AsyncSession,
    identifier: str,
    password_plain: str,
    role: Literal["user", "agent"] = "user",
    **kwargs: Any,
) -> User:
    # prevent duplicates
    existing = await get_user_by_login(db, identifier)
    if existing:
        return existing

    metadata = dict(kwargs.get("metadata_", {}) or {})
    metadata.update(
        {
            "password": pwd_context.hash(password_plain),
            "role": role,
        }
    )

    user = User(
        identifier=identifier,
        metadata_=metadata,
        createdAt=kwargs.get("createdAt"),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(db: AsyncSession, user_id: UUID, **fields: Any) -> Optional[User]:
    user = await db.get(User, user_id)
    if not user:
        return None

    for key, value in fields.items():
        if value is None:
            continue
        if key == "metadata":
            # allow update of metadata dict
            if user.metadata_ is None:
                user.metadata_ = {}
            user.metadata_.update(value)
        elif key == "password_plain":
            if user.metadata_ is None:
                user.metadata_ = {}
            user.metadata_["password"] = pwd_context.hash(value)
        else:
            setattr(user, key, value)

    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, user_id: UUID) -> bool:
    user = await db.get(User, user_id)
    if not user:
        return False
    await db.delete(user)
    await db.commit()
    return True


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
