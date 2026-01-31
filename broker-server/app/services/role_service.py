# services/role_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from models.db import Role
from sqlalchemy import select, delete, update
from typing import List, Optional

class RoleService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_name(self, name: str) -> Optional[Role]:
        result = await self.db.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def get_by_id(self, role_id: int) -> Optional[Role]:
        result = await self.db.execute(select(Role).where(Role.id == role_id))
        return result.scalar_one_or_none()

    async def get_all(self) -> List[Role]:
        result = await self.db.execute(select(Role))
        return result.scalars().all()

    async def create(self, name: str) -> Role:
        role = Role(name=name)
        self.db.add(role)
        await self.db.flush()
        await self.db.refresh(role)
        return role

    async def update(self, role_id: int, name: str) -> Optional[Role]:
        stmt = update(Role).where(Role.id == role_id).values(name=name).returning(Role)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()  # Нет commit — get_db сделает

    async def delete(self, role_id: int) -> bool:
        stmt = delete(Role).where(Role.id == role_id)
        result = await self.db.execute(stmt)
        return result.rowcount > 0  # Нет commit