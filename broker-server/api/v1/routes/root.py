from __future__ import annotations

import base64
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.db import async_session_factory
from database.operations import (
    create_session,
    create_user,
    destroy_session,
    get_user_by_id,
    get_user_by_login,
    verify_password,
)

router = APIRouter(prefix="")


# ---------------------------
# DB helper
# ---------------------------
async def get_db():
    async with async_session_factory() as db:
        yield db


# ---------------------------
# Templates helper
# ---------------------------
def get_templates(request: Request):
    return request.app.state.templates


# ---------------------------
# Current user helper
# ---------------------------
async def get_current_user(
    db=Depends(get_db), session_token: Optional[str] = Cookie(None)
):
    if not session_token:
        return None
    return await _get_current_user(db=db, session_token=session_token)


# ---------------------------
# Главная
# ---------------------------
@router.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user=Depends(get_current_user)):
    return get_templates(request).TemplateResponse(
        "index.html", {"request": request, "user": current_user}
    )


# ---------------------------
# Регистрация
# ---------------------------
@router.get("/register", response_class=HTMLResponse)
async def register_get(request: Request):
    return get_templates(request).TemplateResponse(
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
        return get_templates(request).TemplateResponse(
            "register.html", {"request": request, "error": "Пароли не совпадают"}
        )

    existing = await get_user_by_login(db, username)
    if existing:
        return get_templates(request).TemplateResponse(
            "register.html",
            {"request": request, "error": "Пользователь уже существует"},
        )

    user = await create_user(db, identifier=username, password_plain=password)
    token = await create_session(db, user.id)

    resp = RedirectResponse(url=f"/user/{user.id}", status_code=303)
    resp.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    return resp


# ---------------------------
# Логин
# ---------------------------
@router.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return get_templates(request).TemplateResponse(
        "login.html", {"request": request, "error": None}
    )


@router.post("/login")
async def login_post(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    db=Depends(get_db),
):
    user = await get_user_by_login(db, login)
    if not user:
        return get_templates(request).TemplateResponse(
            "login.html", {"request": request, "error": "Неправильные учётные данные"}
        )

    hashed = (user.metadata_ or {}).get("password")
    if not hashed or not verify_password(password, hashed):
        return get_templates(request).TemplateResponse(
            "login.html", {"request": request, "error": "Неправильные учётные данные"}
        )

    token = await create_session(db, user.id)
    resp = RedirectResponse(url=f"/user/{user.id}", status_code=303)
    resp.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    return resp


# ---------------------------
# Профиль
# ---------------------------
@router.get("/user/{user_id}", response_class=HTMLResponse)
async def profile(
    request: Request,
    user_id: str,
    current_user=Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=403)

    if str(current_user.id) != str(user_id):
        raise HTTPException(status_code=403)

    return get_templates(request).TemplateResponse(
        "profile.html", {"request": request, "user": current_user, "editable": True}
    )


# ---------------------------
# Logout
# ---------------------------
@router.get("/logout")
async def logout(
    db=Depends(get_db),
    session_token: Optional[str] = Cookie(None),
):
    if session_token:
        await destroy_session(db=db, session_token=session_token)

    resp = RedirectResponse(url="/", status_code=302)
    resp.delete_cookie("session_token")
    return resp
