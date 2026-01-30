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
