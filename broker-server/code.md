Отлично, теперь всё понятно 💪
Ты права: **endpoints/root.py и operations.py сейчас полностью не соответствуют твоим SQLAlchemy моделям** (и вообще написаны под SQLModel + email + 2FA).
Делаем правильно:

* **2FA удаляем полностью**
* **email удаляем полностью**
* **SQLModel удаляем полностью**
* **переходим на Async SQLAlchemy (AsyncSession)**
* **user.password_hash / otp_secret / is_2fa_enabled — больше не существует**
* **пароль и роль живут в `User.metadata_`**

Ниже я даю **готовые исправленные версии**:

1. `operations.py` (полностью переписан)
2. `api/v1/routes/root.py` (переписан без 2FA, без email)

---

## 1) Новый `operations.py` (Async SQLAlchemy)

📌 Что делает:

* CRUD пользователей (через `identifier`)
* сессии по cookie `session_token` (хранятся в БД)
* `get_current_user()` работает через session_token
* пароль хранится в `metadata_["password"]`
* роль хранится в `metadata_["role"]`

### `schemas/database_models.py` — добавь модель Session

Т.к. у тебя в operations есть SessionModel, но таблицы нет — нужно добавить:

```py
# schemas/database_models.py

import uuid
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifier = Column(String, nullable=False, unique=True)
    metadata_ = Column("metadata", JSONB, nullable=False, default=dict)
    createdAt = Column(String)


class SessionModel(Base):
    __tablename__ = "sessions"

    token = Column(String, primary_key=True)
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    created = Column(DateTime(timezone=False), nullable=False)
    expires = Column(DateTime(timezone=False), nullable=False)

    user = relationship("User")
```

> Если у тебя таблица `sessions` уже есть, но с другим названием/полями — скажи, я подгоню под твою схему.

---

### `operations.py` (полностью заменить)

```py
# operations.py
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional, Literal
from uuid import UUID

from fastapi import Cookie
from passlib.context import CryptContext
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.db import async_session_factory
from schemas.database_models import User, SessionModel


class UserRole:
    USER: str = "user"
    AGENT: str = "agent"


pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
SECRET_KEY = os.getenv("SECRET_KEY", "change_me")


@dataclass
class UserMetadata:
    password: str  # raw password input, then stored as hash
    role: Literal["user", "agent"] = UserRole.USER

    def to_dict(self) -> dict[str, Any]:
        return {"password": self.password, "role": self.role}


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

    # Если пришёл объект Cookie, возьми его value
    if not isinstance(session_token, str):
        session_token = getattr(session_token, "value", None)
    if not session_token:
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
    role: Literal["user", "agent"] = UserRole.USER,
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
```

---

## 2) Новый `api/v1/routes/root.py` (без 2FA и email)

Это твой `root.py`, но:

* удалены `pyotp`, `qrcode`, все `/2fa_*`
* регистрация только `username + password`
* логин по `identifier`
* password берём из `user.metadata_["password"]`

```py
# api/v1/routes/root.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.db import async_session_factory
from operations import (
    create_session,
    create_user,
    destroy_session,
    get_current_user,
    get_user_by_login,
    verify_password,
)

router = APIRouter(prefix="")


async def get_db():
    async with async_session_factory() as db:
        yield db


@router.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = exc.status_code
    messages = {
        404: "Страница не найдена",
        403: "Доступ запрещён",
        500: "Внутренняя ошибка сервера",
        502: "Плохой шлюз",
    }
    message = messages.get(code, exc.detail or "Произошла ошибка")
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "code": code, "message": message},
        status_code=code,
    )


@router.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "code": 500, "message": "Ошибка сервера"},
        status_code=500,
    )


# Главная
@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db=Depends(get_db),
):
    current_user = await get_current_user(db=db)
    return templates.TemplateResponse(
        "index.html", {"request": request, "user": current_user}
    )


# Регистрация
@router.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return templates.TemplateResponse(
        "register.html", {"request": request, "error": None}
    )


@router.post("/register")
async def register_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db=Depends(get_db),
):
    if password != confirm_password:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Пароли не совпадают"}
        )

    existing = await get_user_by_login(db, username)
    if existing:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Пользователь уже существует"},
        )

    user = await create_user(db=db, identifier=username, password_plain=password)

    resp = RedirectResponse(url=f"/user/{user.id}", status_code=303)
    token = await create_session(db, user.id)
    resp.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    return resp


# Логин
@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login")
async def login_post(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    db=Depends(get_db),
):
    user = await get_user_by_login(db, login)
    if not user:
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Неправильные учётные данные"}
        )

    hashed = (user.metadata_ or {}).get("password")
    if not hashed or not verify_password(password, hashed):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Неправильные учётные данные"}
        )

    resp = RedirectResponse(url=f"/user/{user.id}", status_code=303)
    token = await create_session(db, user.id)
    resp.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    return resp


# Профиль
@router.get("/user/{user_id}", response_class=HTMLResponse)
async def profile(
    request: Request,
    user_id: str,
    db=Depends(get_db),
):
    current_user = await get_current_user(db=db)
    if not current_user:
        raise HTTPException(status_code=403)

    # разрешаем смотреть только себя (или админа)
    if str(current_user.id) != str(user_id):
        # если хочешь оставить админа — можно по роли:
        # if (current_user.metadata_ or {}).get("role") != "agent": ...
        raise HTTPException(status_code=403)

    return templates.TemplateResponse(
        "profile.html", {"request": request, "user": current_user, "editable": True}
    )


# Logout
@router.get("/logout")
async def logout(request: Request, db=Depends(get_db)):
    token = request.cookies.get("session_token")
    await destroy_session(db=db, session_token=token)
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_token")
    return response
```

---

## 3) Что ещё надо удалить (чтобы проект реально не падал)

### Удали импорты/зависимости:

* `pyotp`
* `qrcode`
* `PIL` (если аватаров больше нет)
* `sqlmodel` везде

### Удали шаблоны:

* `2fa_setup.html` (если он у тебя есть)

### Удали маршруты:

* `/2fa_check`
* `/user/{id}/2fa`
* `/user/{id}/2fa_enable`
* `/user/{id}/2fa_disable`

---

## 4) Твои текущие главные ошибки в operations.py (почему ломалось)

1. Используется **SQLModel Session + select**, но у тебя **Async SQLAlchemy**
2. `user_id: int`, но у тебя `UUID`
3. `metadata` поле называется `metadata_` (иначе конфликт с SQLAlchemy metadata)
4. email отсутствует, а root.py везде требует `email`
5. password_hash отсутствует, у тебя пароль в JSONB `metadata_["password"]`

---

Если хочешь — я могу также:

* переписать `profile/edit` (если оно тебе нужно)
* добавить endpoints для Threads и LangGraphState (т.к. они у тебя уже в моделях)
