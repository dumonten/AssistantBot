# utils/security.py
from passlib.context import CryptContext

# Контекст для хеширования паролей
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    Хеширует пароль для хранения в БД.
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Проверяет соответствие введенного пароля и хеша из БД.
    """
    return pwd_context.verify(plain_password, hashed_password)
