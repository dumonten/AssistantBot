"""
Main application entry point for the Voice Analytics LLM service.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from setproctitle import setproctitle

from api.v1.router import api_router
from core.config import settings
from core.db import engine, init_db

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
    app.state.templates = Jinja2Templates(
        directory=str(settings.data_dir / "templates")
    )

    yield

    await engine.dispose()


# Initialize FastAPI application with project configuration
app = FastAPI(
    lifespan=lifespan,
)
app.mount(
    "/resources",
    StaticFiles(directory=str(settings.data_dir / "resources")),
    name="resources",
)
app.mount("/static", StaticFiles(directory=settings.data_dir / "static"), name="static")

app.include_router(api_router)

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


"""
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = exc.status_code
    messages = {
        404: "Страница не найдена",
        403: "Доступ запрещён",
        500: "Внутренняя ошибка сервера",
        502: "Плохой шлюз",
    }
    message = messages.get(code, exc.detail or "Произошла ошибка")
    return Jinja2Templates(
        directory=str(settings.data_dir / "templates")
    ).TemplateResponse(
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
"""
