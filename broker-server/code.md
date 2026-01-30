=== main.py ===

"""
Main application entry point for the Voice Analytics LLM service.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from setproctitle import setproctitle

from core.config import settings
from core.db import engine, init_db
from core.logging import LoggingMiddleware, setup_logging

setup_logging()
setproctitle(settings.PROCESS_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager for initializing and cleaning up resources.

    Initializes the agent service and all registered agents, making them
    available in the application state, and cleans up resources on shutdown.

    Args:
        app: FastAPI application instance
    """
    await init_db()
    yield
    await engine.dispose()


# Initialize FastAPI application with project configuration
app = FastAPI(
    lifespan=lifespan,
)
app.mount(
    "/resources",
    StaticFiles(directory=settings.data_dir / "resources"),
    name="resources",
)
app.mount("/static", StaticFiles(directory=settings.data_dir / "static"), name="static")

templates = Jinja2Templates(directory=settings.data_dir / "templates")


# Add logging middleware for request/response logging
app.add_middleware(LoggingMiddleware)


if __name__ == "__main__":

    import uvicorn

    logger.info("Running app...")
    logger.info(
        f"{settings.APP_NAME} listening on http://{settings.SERVER_HOST}:{settings.SERVER_PORT}"
    )
    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.LOG_LEVEL.upper() == "DEBUG",
        log_level=settings.LOG_LEVEL.lower(),
        workers=settings.SERVER_WORKERS,
    )


=== router.py ===

from fastapi import APIRouter

from api.v1.routes import root

# Main API router with common configuration
api_router = APIRouter(
    prefix="",
    responses={404: {"description": "Endpoint not found"}},
)

# Include sub-routers for different API sections
api_router.include_router(root.router, tags=["Root"])


=== root.py ===

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


=== config.py ===

from datetime import datetime
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
    )

    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 9040
    SERVER_WORKERS: int = 1

    DB_HOST: str
    DB_PORT: str
    DB_USER: str
    DB_PASSWORD: str
    DB_NAME: str

    MAX_DB_CONNECTION_RETRIES: int = 10

    CHAINLIT_APP_URL: str
    APP_DATA_DIR_NAME: str
    APP_NAME: str
    PROCESS_NAME: str

    LOG_LEVEL: str = "INFO"
    LOG_ROTATION: str = "1 day"
    LOG_RETENTION: str = "1 month"
    LOG_TO_FILE: bool = True
    LOG_DIR: Path = Path("logs")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def log_file_path(self) -> Path:
        today = datetime.now().strftime("%d-%m-%Y")
        return self.LOG_DIR / f"{today}.log"

    @property
    def data_dir(self) -> Path:
        if not hasattr(self, "_data_dir"):
            if self.APP_DATA_DIR_NAME is None:
                raise ValueError("APP_DATA_DIR_NAME is not set")
            self._data_dir = Path.cwd() / self.APP_DATA_DIR_NAME
            if not self._data_dir.exists():
                raise ValueError(f"Data directory does not exist: {self._data_dir}")
        return self._data_dir


settings: Settings = Settings()


=== db.py ===

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from core.config import settings

Base = declarative_base()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)

async_session_factory = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def init_db() -> None:
    # 1) ping
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    # 2) create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


=== logging.py ===

import json
import sys
import time
from typing import Callable

from fastapi import Request
from fastapi import Response as FastAPIResponse
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for detailed logging of HTTP requests and responses.

    Logs request method, URL, client address, request body, response body,
    and processing time for debugging and monitoring purposes.
    """

    TRUNCATE_CHAR_LIMIT: int = 1000

    async def dispatch(self, request: Request, call_next: Callable) -> FastAPIResponse:
        """
        Process the request and log details before and after processing.

        Args:
            request: Incoming request object
            call_next: Next middleware/function in the chain

        Returns:
            Processed response object
        """
        start_time = time.time()
        # Get client info
        client_host = request.client.host if request.client else "unknown"
        client_port = request.client.port if request.client else "unknown"
        remote_addr = f"{client_host}:{client_port}"
        # Log request details
        request_body_log = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                request._body = body
                if body:
                    content_type = request.headers.get("content-type", "").lower()
                    if "application/json" in content_type:
                        try:
                            request_body = json.loads(body)
                            request_body_log = json.dumps(
                                request_body, indent=None, ensure_ascii=False
                            )
                        except json.JSONDecodeError:
                            request_body_log = body.decode("utf-8", errors="replace")
                    elif content_type.startswith("text/"):
                        request_body_log = body.decode("utf-8", errors="replace")
                    else:
                        request_body_log = f"Type: {content_type} - not logged"
            except Exception as e:
                logger.error(f"Error reading request body: {e}")
                request_body_log = "[Error reading body]"
        if request_body_log and len(request_body_log) > self.TRUNCATE_CHAR_LIMIT:
            request_body_log = (
                request_body_log[: self.TRUNCATE_CHAR_LIMIT] + "... (truncated)"
            )
        logger.info(
            f"{request.method} {request.url.path} | {remote_addr} | Request Body: {request_body_log}"
        )
        # Process the request
        response = await call_next(request)
        # Capture and log response body (buffering it for logging)
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # Rebuild the body iterator to avoid consumption
        async def new_body_iterator():
            yield body

        response.body_iterator = new_body_iterator()
        response_body_log = None
        if body:
            content_type = response.headers.get("content-type", "").lower()
            if "application/json" in content_type:
                try:
                    response_body = json.loads(body.decode("utf-8", errors="replace"))
                    response_body_log = json.dumps(
                        response_body, indent=None, ensure_ascii=False
                    )
                except Exception as e:
                    logger.error(f"Error parsing JSON response body: {e}")
                    response_body_log = "[Invalid JSON]"
            elif content_type.startswith("text/"):
                response_body_log = body.decode("utf-8", errors="replace")
            else:
                response_body_log = f"Type: {content_type} - not logged"
        if response_body_log and len(response_body_log) > self.TRUNCATE_CHAR_LIMIT:
            response_body_log = (
                response_body_log[: self.TRUNCATE_CHAR_LIMIT] + "... (truncated)"
            )
        process_time = time.time() - start_time
        log_msg = f"{response.status_code} | {request.method} {request.url.path} | {remote_addr} | Time: {process_time:.4f}s | Response Body: {response_body_log}"
        if response.status_code == 200:
            logger.info(log_msg)
        else:
            logger.error(log_msg)
        return response


def setup_logging():
    """
    Configure the application logging with console and file handlers.

    Sets up logging with the configured log level, adds console handler with
    colorization, and file handler with rotation and retention policies.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        colorize=True,
    )

    logger.add(
        settings.log_file_path,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        level=settings.LOG_LEVEL,
        enqueue=True,
    )


=== operations.py ===

from datetime import datetime
from typing import Optional

from passlib.context import CryptContext
from sqlmodel import Session, select

from schemas.database_models import User


class UserRole:
    USER: str = "user"
    AGENT: str = "agent"


class UserMetadata:
    password: str  # At first it is raw hash, and then hash
    role: Literal[UserRole]


pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


SECRET_KEY = os.getenv("SECRET_KEY", "change_me")


# Создание сессии и запись в БД
def create_session(user_id: int) -> str:
    token = base64.urlsafe_b64encode(os.urandom(24)).decode()
    expires = datetime.utcnow() + timedelta(days=7)  # сессия живёт 7 дней
    create_session_db(user_id=user_id, token=token, expires=expires)
    return token


# Получение текущего пользователя по cookie
def get_current_user(session_token: Optional[str] = Cookie(None)):
    if not session_token:
        return None
    session = get_session_by_token(session_token)
    if not session:
        return None
    return get_user_by_id(session.user_id)


# Удаление сессии (разлогин)
def destroy_session(session_token: Optional[str] = Cookie(None)):
    if session_token:
        delete_session_db(session_token)

def get_session():
    return Session(engine)


# ✅ Создание сессии
def create_session_db(user_id: int, token: str, expires: datetime) -> SessionModel:
    with get_session() as s:
        session = SessionModel(
            token=token, user_id=user_id, created=datetime.utcnow(), expires=expires
        )
        s.add(session)
        s.commit()
        s.refresh(session)
        return session


# ✅ Получение сессии по токену
def get_session_by_token(token: str) -> Optional[SessionModel]:
    with get_session() as s:
        statement = select(SessionModel).where(SessionModel.token == token)
        result = s.exec(statement).first()
        if result and result.expires > datetime.utcnow():
            return result
        return None


# ✅ Удаление сессии
def delete_session_db(token: str) -> bool:
    with get_session() as s:
        statement = select(SessionModel).where(SessionModel.token == token)
        result = s.exec(statement).first()
        if not result:
            return False
        s.delete(result)
        s.commit()
        return True


# Пользователи
def get_user_by_id(user_id: int) -> Optional[User]:
    with get_session() as s:
        return s.get(User, user_id)


def get_user_by_login(login: str) -> Optional[User]:
    with get_session() as s:
        statement = select(User).where(User.identifier == login)
        return s.exec(statement).first()


def list_users() -> list[User]:
    with get_session() as s:
        statement = select(User).order_by(User.id)
        return s.exec(statement).all()


def create_user(identifier: str, user_metadata: UserMetadata, **kwargs) -> User:
    with get_session() as s:
        user_metadata.password = pwd_context.hash(user_metadata.password)
        user = User(
            identifier=identifier, metadata=user_metadata.model_dump() ** kwargs
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


def create_user_raw(id: int, identifier: str, user_metadata: UserMetadata,, **kwargs) -> User:
    with get_session() as s:
        existing = s.get(User, id)
        if existing:
            return existing
        user_metadata.password = pwd_context.hash(user_metadata.password)
        user = User(
            identifier=identifier, metadata=user_metadata.model_dump() ** kwargs
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


def update_user(user_id: int, **fields) -> Optional[User]:
    with get_session() as s:
        user = s.get(User, user_id)
        if not user:
            return None
        for key, value in fields.items():
            if value is not None:
                setattr(user, key, value)
        s.add(user)
        s.commit()
        s.refresh(user)
        return user


def delete_user(user_id: int) -> bool:
    with get_session() as s:
        user = s.get(User, user_id)
        if not user:
            return False
        s.delete(user)
        s.commit()
        return True


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


=== database_models.py ===

import uuid

from sqlalchemy import JSON, Column, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from core.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifier = Column(String, nullable=False, unique=True)
    metadata_ = Column("metadata", JSONB, nullable=False)
    createdAt = Column(String)


class Thread(Base):
    __tablename__ = "threads"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    createdAt = Column(String)
    name = Column(String)
    userId = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    userIdentifier = Column(String)
    tags = Column(ARRAY(String))
    metadata_ = Column("metadata", JSONB)

    user = relationship("User", backref="threads")


class LangGraphState(Base):
    __tablename__ = "langgraphs"

    thread_id = Column(String, primary_key=True)
    state = Column(JSON, nullable=False)
    workflow = Column(String, nullable=False)


