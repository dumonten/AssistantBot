# services/user_service.py (completed with full CRUD)
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import User
from services.role_service import RoleService
from sqlalchemy import select, delete, update
from typing import List, Optional

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_login(self, login: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.login == login))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_all(self) -> List[User]:
        result = await self.db.execute(select(User))
        return result.scalars().all()

    async def create(self, login: str, hashed_password: str) -> User:
        user = User(login=login, hashed_password=hashed_password)
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update(self, user_id: int, login: Optional[str] = None, hashed_password: Optional[str] = None, is_active: Optional[bool] = None) -> Optional[User]:
        updates = {}
        if login is not None:
            updates["login"] = login
        if hashed_password is not None:
            updates["hashed_password"] = hashed_password
        if is_active is not None:
            updates["is_active"] = is_active
        if not updates:
            return await self.get_by_id(user_id)
        stmt = update(User).where(User.id == user_id).values(**updates).returning(User)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()  # Нет commit

    async def delete(self, user_id: int) -> bool:
        stmt = delete(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.rowcount > 0  # Нет commit

    # Additional methods for role management
    async def add_role_to_user(self, user_id: int, role_id: int) -> bool:
        user = await self.get_by_id(user_id)
        role = await RoleService(self.db).get_by_id(role_id)
        if user and role and role not in user.roles:
            user.roles.append(role)
            await self.db.flush()  # Flush для M2M, если нужно сразу увидеть изменения
            return True
        return False

    async def remove_role_from_user(self, user_id: int, role_id: int) -> bool:
        user = await self.get_by_id(user_id)
        role = await RoleService(self.db).get_by_id(role_id)
        if user and role and role in user.roles:
            user.roles.remove(role)
            await self.db.flush()
            return True
        return False
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_login(self, login: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.login == login))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_all(self) -> List[User]:
        result = await self.db.execute(select(User))
        return result.scalars().all()

    async def create(self, login: str, hashed_password: str) -> User:
        user = User(login=login, hashed_password=hashed_password)
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def update(self, user_id: int, login: Optional[str] = None, hashed_password: Optional[str] = None, is_active: Optional[bool] = None) -> Optional[User]:
        updates = {}
        if login is not None:
            updates["login"] = login
        if hashed_password is not None:
            updates["hashed_password"] = hashed_password
        if is_active is not None:
            updates["is_active"] = is_active
        if not updates:
            return await self.get_by_id(user_id)
        stmt = update(User).where(User.id == user_id).values(**updates).returning(User)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.scalar_one_or_none()

    async def delete(self, user_id: int) -> bool:
        stmt = delete(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount > 0

    # Additional methods for role management
    async def add_role_to_user(self, user_id: int, role_id: int) -> bool:
        user = await self.get_by_id(user_id)
        role = await RoleService(self.db).get_by_id(role_id)
        if user and role and role not in user.roles:
            user.roles.append(role)
            await self.db.flush()
            return True
        return False

    async def remove_role_from_user(self, user_id: int, role_id: int) -> bool:
        user = await self.get_by_id(user_id)
        role = await RoleService(self.db).get_by_id(role_id)
        if user and role and role in user.roles:
            user.roles.remove(role)
            await self.db.flush()
            return True
        return False