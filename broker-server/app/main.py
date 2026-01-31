import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from setproctitle import setproctitle
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.v1.router import api_router
from core.config import settings
from core.db import AsyncSessionLocal, engine
from dev.first_run import create_default_admin

setproctitle(settings.PROCESS_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan приложения: инициализация ресурсов и их закрытие.
    """
    app.state.templates = Jinja2Templates(
        directory=str(settings.data_dir / "templates")
    )

    # Создаем админа, если его нет
    async with AsyncSessionLocal() as session:
        await create_default_admin(session)

    yield

    await engine.dispose()


app = FastAPI(lifespan=lifespan)

app.mount(
    "/static",
    StaticFiles(directory=str(settings.data_dir / "static")),
    name="static",
)

app.include_router(api_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    messages = {
        404: "Страница не найдена",
        403: "Доступ запрещён",
        500: "Внутренняя ошибка сервера",
        502: "Плохой шлюз",
    }
    message = messages.get(exc.status_code, exc.detail or "Произошла ошибка")
    return request.app.state.templates.TemplateResponse(
        "error.html",
        {"request": request, "code": exc.status_code, "message": message},
        status_code=exc.status_code,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled exception: {exc}")
    return request.app.state.templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "code": 500,
            "message": "Произошла внутренняя ошибка сервера",
        },
        status_code=500,
    )


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.LOG_LEVEL.upper() == "DEBUG",
        log_level=settings.LOG_LEVEL.lower(),
        workers=settings.SERVER_WORKERS,
    )
