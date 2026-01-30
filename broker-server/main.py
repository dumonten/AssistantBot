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
    app.state.templates = Jinja2Templates(directory=str(settings.data_dir / "templates"))

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
