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


def get_templates(request: Request):
    return request.app.state.templates
    
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
    return get_templates(request).TemplateResponse(
        "error.html",
        {"request": request, "code": code, "message": message},
        status_code=code,
    )


@router.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return get_templates(request).TemplateResponse(
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
    return get_templates(request).TemplateResponse(
        "index.html", {"request": request, "user": current_user}
    )


# Регистрация
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
    return get_templates(request).TemplateResponse("login.html", {"request": request, "error": None})


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

    return get_templates(request).TemplateResponse(
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
