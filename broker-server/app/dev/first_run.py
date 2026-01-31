from sqlalchemy.ext.asyncio import AsyncSession

from models.db import Role, User
from services.role_service import RoleService
from services.user_service import UserService
from utils.security import hash_password, verify_password


async def create_default_admin(session: AsyncSession):
    role_svc = RoleService(session)
    user_svc = UserService(session)

    # Создаем роль admin
    admin_role = await role_svc.get_by_name("admin")
    if not admin_role:
        admin_role = await role_svc.create("admin")
        await session.commit()

    # Создаем пользователя admin
    admin_user = await user_svc.get_by_login("admin")
    if not admin_user:
        hashed = hash_password("admin123")  # пароль по умолчанию
        admin_user = await user_svc.create("admin", hashed)
        await user_svc.add_role_to_user(admin_user.id, admin_role.id)
        await session.commit()
