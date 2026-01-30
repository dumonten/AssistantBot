# app/main.py
import base64
import io
from binascii import Error as B64DecodeError
from contextlib import asynccontextmanager
from io import BytesIO
from typing import Optional

import pyotp
import qrcode
from app.auth import create_session, destroy_session, get_current_user
from app.crud import (
    create_user,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_login,
    list_users,
    pwd_context,
    update_user,
    verify_password,
)
from app.database import engine
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, UnidentifiedImageError
from sqlmodel import SQLModel
from starlette.exceptions import HTTPException as StarletteHTTPException

router = APIRouter(prefix="")


@router.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = exc.status_code
    messages = {
        404: "Страница не найдена",
        403: "Доступ запрещён",
        500: "Внутренняя ошибка сервера",
        502: "Плохой шлюз",
    }
    message = messages.get(
        code, exc.detail if getattr(exc, "detail", None) else "Произошла ошибка"
    )
    # возвращаем страницу ошибки с нужным кодом
    return templates.TemplateResponse(
        "error.html",
        {"request": request, "code": code, "message": message},
        status_code=code,
    )


# Обработчик всех прочих непойманных исключений (500)
@router.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    # здесь вы можете залогировать `exc`, если нужно
    tmp = request.cookies.get("tmp_user")
    if not tmp:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "code": 520, "message": "Неизвестная ошибка"},
            status_code=520,
        )
    user_id = int(tmp)
    user = get_user_by_id(user_id)

    return templates.TemplateResponse(
        "error.html",
        {"request": request, "code": 500, "message": "Ошибка сервера"},
        status_code=500,
    )


# Главная
@router.get("/", response_class=HTMLResponse)
def index(request: Request, current_user=Depends(get_current_user)):
    return templates.TemplateResponse(
        "index.html", {"request": request, "user": current_user}
    )


# Регистрация (GET/POST)
@router.get("/register", response_class=HTMLResponse)
def register_get(request: Request):
    return templates.TemplateResponse(
        "register.html", {"request": request, "error": None}
    )


@router.post("/register")
def register_post(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
):
    # Валидация паролей
    if password != confirm_password:
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Пароли не совпадают"}
        )

    # Проверка существования email
    if get_user_by_email(email):
        return templates.TemplateResponse(
            "register.html", {"request": request, "error": "Email уже зарегистрирован"}
        )

    # Создаём пользователя. Передаём пустые optional-поля явно.
    # Внутри create_user ожидаем identifier/email/password_plain — поэтому мапим username -> identifier.
    user = create_user(
        identifier=username,
        email=email,
        password_plain=password,
        birthday=None,
        bio="",
        phone="",
    )

    # Логиним пользователя: создаём сессию и ставим cookie
    resp = RedirectResponse(url=f"/user/{user.id}", status_code=303)
    token = create_session(user.id)
    resp.set_cookie("session_token", token, httponly=True)
    return resp


# Логин (оставляем как было)
@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


# Логин
@router.post("/login")
def login_post(request: Request, login: str = Form(...), password: str = Form(...)):
    user = get_user_by_login(login)
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html", {"request": request, "error": "Неправильные учётные данные"}
        )

    # Если у пользователя включена 2FA
    if user.is_2fa_enabled:
        # Сохраняем временно id пользователя в куке и перенаправляем на страницу ввода кода
        resp = RedirectResponse(url="/2fa_check", status_code=303)
        resp.set_cookie("tmp_user", str(user.id), httponly=True)
        return resp

    # Если 2FA нет, создаём сессию сразу
    resp = RedirectResponse(url=f"/user/{user.id}", status_code=303)
    token = create_session(user.id)
    resp.set_cookie(
        key="session_token",
        value=token,
        max_age=60 * 60 * 24 * 30,
        httponly=True,
        samesite="lax",
    )
    return resp


# 2FA проверка (GET показывает форму, POST проверяет код)
@router.get("/2fa_check", response_class=HTMLResponse)
def twofa_get(request: Request, user_id: Optional[int] = None):
    # Универсальная страница: если user_id указан — это этап настройки (редиректят на /user/.../2fa),
    # если нет — это проверка при логине (checking=True)
    return templates.TemplateResponse(
        "2fa_setup.html", {"request": request, "checking": True, "error": None}
    )


@router.post("/2fa_check")
def twofa_post(request: Request, code: str = Form(...)):
    tmp = request.cookies.get("tmp_user")
    if not tmp:
        return RedirectResponse("/login", status_code=303)
    user_id = int(tmp)
    user = get_user_by_id(user_id)
    if not user or not user.otp_secret:
        return templates.TemplateResponse(
            "2fa_setup.html",
            {"request": request, "checking": True, "error": "2FA не настроена"},
        )

    totp = pyotp.TOTP(user.otp_secret)
    if not totp.verify(code):
        return templates.TemplateResponse(
            "2fa_setup.html",
            {"request": request, "checking": True, "error": "Неверный код"},
        )

    # Всё верно — создаём сессию
    resp = RedirectResponse(url=f"/user/{user.id}", status_code=303)
    token = create_session(user.id)
    resp.set_cookie("session_token", token, httponly=True)
    resp.delete_cookie("tmp_user")
    return resp


# Профиль
@router.get("/user/{user_id}", response_class=HTMLResponse)
def profile(request: Request, user_id: int, current_user=Depends(get_current_user)):
    # Проверка прав: если не залогинен или заходит в чужой профиль, отдаем 403
    if not current_user or not (current_user.id == user_id or current_user.id == 1):
        raise HTTPException(status_code=403)

    # Получаем пользователя по ID
    user = get_user_by_id(user_id)
    # Если такого пользователя нет, отдаем 404
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    # editable только для самого пользователя или администратора
    editable = current_user.id == user.id or current_user.id == 1

    return templates.TemplateResponse(
        "profile.html", {"request": request, "user": user, "editable": editable}
    )


@router.get("/user/{user_id}/edit", response_class=HTMLResponse)
def edit_profile_get(
    request: Request, user_id: int, current_user=Depends(get_current_user)
):
    user = get_user_by_id(user_id)
    if not user:
        return Response("Пользователь не найден", status_code=404)

    editable = bool(
        current_user and (current_user.id == user_id or current_user.id == 1)
    )
    return templates.TemplateResponse(
        "edit_profile.html",
        {"request": request, "user": user, "error": None, "editable": editable},
    )


@router.post("/user/{user_id}/edit")
def edit_profile_post(
    request: Request,
    user_id: int,
    identifier: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    password: Optional[str] = Form(None),
    password_confirm: Optional[str] = Form(None),
    birthday: Optional[str] = Form(None),
    bio: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    avatar_b64: Optional[str] = Form(None),
    current_user=Depends(get_current_user),
):
    # САМАЯ ВАЖНАЯ ЧАСТЬ: жёсткая проверка прав
    if not current_user or not (current_user.id == user_id or current_user.id == 1):
        # вызовет 403 и отправит на error.html
        raise HTTPException(status_code=403)
    # Получаем пользователя по ID
    user = get_user_by_id(user_id)
    # Если такого пользователя нет, отдаем 404
    if not user:
        # вызовет 404 и отправит на error.html
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    # далее — твоя логика валидации/обновления (как было)
    if password and password != password_confirm:
        user = get_user_by_id(user_id)
        return templates.TemplateResponse(
            "edit_profile.html",
            {
                "request": request,
                "user": user,
                "error": "Пароли не совпадают",
                "editable": True,
            },
        )

    fields = {}
    if identifier is not None:
        fields["identifier"] = identifier
    if email is not None:
        fields["email"] = email
    if birthday:
        fields["birthday"] = birthday
    if bio is not None:
        fields["bio"] = bio
    if phone is not None:
        fields["phone"] = phone
    if password:
        fields["password_hash"] = pwd_context.hash(password)

    if avatar_b64:
        # print("[DEBUG] avatar_b64=='" + avatar_b64 + "'")
        if avatar_b64 == "__DELETE__":
            fields["avatar"] = None
        else:
            # Декодируем исходный base64
            try:
                raw_data = base64.b64decode(avatar_b64)
                img = Image.open(BytesIO(raw_data))

                if img.mode in ("RGBA", "LA") or ("transparency" in img.info):
                    img = img.convert("RGBA")
                    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
                    img = Image.alpha_composite(bg, img)

                img = img.convert("RGB")
                img.thumbnail((256, 256))

                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=95)
                compressed_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
                fields["avatar"] = compressed_b64
            except (B64DecodeError, UnidentifiedImageError, Exception) as e:
                return templates.TemplateResponse(
                    "edit_profile.html",
                    {
                        "request": request,
                        "user": user,
                        "error": f"{e.__class__.__name__}: {e}",
                        "editable": True,
                    },
                )

    update_user(user_id, **fields)
    return RedirectResponse(f"/user/{user_id}", status_code=303)


# 2FA setup (enable/disable)
@router.post("/2fa_check")
def twofa_post(request: Request, code: str = Form(...)):
    tmp = request.cookies.get("tmp_user")
    if not tmp:
        return RedirectResponse("/login")
    user_id = int(tmp)
    user = get_user_by_id(user_id)
    if not user or not user.otp_secret:
        return templates.TemplateResponse(
            "2fa_setup.html",
            {"request": request, "checking": True, "error": "2FA не настроена"},
        )
    totp = pyotp.TOTP(user.otp_secret)
    if not totp.verify(code):
        return templates.TemplateResponse(
            "2fa_setup.html",
            {"request": request, "checking": True, "error": "Неверный код"},
        )

    # ✅ Если код верный — включаем 2FA, если она была в процессе настройки
    if not user.is_2fa_enabled:
        update_user(user_id, is_2fa_enabled=True)

    # ✅ создаём сессию
    resp = RedirectResponse(url=f"/user/{user.id}", status_code=303)
    token = create_session(user.id)
    resp.set_cookie("session_token", token, httponly=True)
    resp.delete_cookie("tmp_user")
    return resp


@router.get("/user/{user_id}/2fa", response_class=HTMLResponse)
def setup_2fa_get(
    request: Request, user_id: int, current_user=Depends(get_current_user)
):
    if not current_user or not (current_user.id == user_id or current_user.id == 1):
        return RedirectResponse("/login")
    user = get_user_by_id(user_id)
    if not user:
        return Response("Пользователь не найден", status_code=404)
    # если нет секрета — генерируем и сохраняем
    if not user.otp_secret:
        secret = pyotp.random_base32()
        update_user(user_id, otp_secret=secret)
        user = get_user_by_id(user_id)
    otpauth = pyotp.totp.TOTP(user.otp_secret).provisioning_uri(
        name=user.email, issuer_name="FastAPIApp"
    )
    img = qrcode.make(otpauth)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode()
    return templates.TemplateResponse(
        "2fa_setup.html",
        {
            "request": request,
            "user": current_user,
            "qr": img_b64,
            "secret": user.otp_secret,
            "checking": False,
        },
    )


@router.post("/user/{user_id}/2fa_disable")
def disable_2fa(user_id: int, current_user=Depends(get_current_user)):
    if not current_user or not (current_user.id == user_id or current_user.id == 1):
        return RedirectResponse("/login")
    update_user(user_id, is_2fa_enabled=False, otp_secret=None)
    return RedirectResponse(f"/user/{user_id}", status_code=303)


@router.post("/user/{user_id}/2fa_enable")
def enable_2fa(
    user_id: int, code: str = Form(...), current_user=Depends(get_current_user)
):
    if not current_user or not (current_user.id == user_id or current_user.id == 1):
        return RedirectResponse("/login")
    user = get_user_by_id(user_id)
    if not user or not user.otp_secret:
        return RedirectResponse(f"/user/{user_id}/2fa")
    totp = pyotp.TOTP(user.otp_secret)
    if totp.verify(code):
        update_user(user_id, is_2fa_enabled=True)
    return RedirectResponse(f"/user/{user_id}", status_code=303)


# Админ: список пользователей, создание, удаление
@router.get("/admin", response_class=HTMLResponse)
def admin_panel(request: Request, current_user=Depends(get_current_user)):
    if not current_user or current_user.id != 1:
        return RedirectResponse("/login")
    users = list_users()
    return templates.TemplateResponse(
        "admin.html", {"request": request, "users": users}
    )


@router.post("/admin/create")
def admin_create(
    identifier: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    current_user=Depends(get_current_user),
):
    if not current_user or current_user.id != 1:
        return RedirectResponse("/login")
    create_user(identifier=identifier, email=email, password_plain=password)
    return RedirectResponse("/admin")


@router.post("/admin/delete")
def admin_delete(user_id: int = Form(...), current_user=Depends(get_current_user)):
    if not current_user or current_user.id != 1:
        return RedirectResponse("/login")
    if user_id == 1:
        return RedirectResponse("/admin")
    delete_user(user_id)
    return RedirectResponse("/admin")


# Logout
@router.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("session_token")
    if token:
        destroy_session(token)
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("session_token")
    return response


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9045,
        workers=1,
    )
