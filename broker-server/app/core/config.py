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
            f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @property
    def async_database_url(self) -> str:
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
print(settings.database_url)
