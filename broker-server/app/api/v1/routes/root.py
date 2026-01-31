from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse

from api.deps import RoleServiceDep, UserServiceDep
from utils.security import hash_password, verify_password

router = APIRouter(prefix="")


# ----------------------
# Главная страница — всегда редирект на /login
# ----------------------
@router.get("/")
async def index():
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# ----------------------
# Регистрация
# ----------------------
@router.get("/register")
async def register_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "register.html",
        {"request": request, "error": None, "title": "Регистрация", "user": None},
    )


@router.post("/register")
async def register_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    user_service: UserServiceDep = Depends(),
):
    error = None

    if password != confirm_password:
        error = "Пароли не совпадают"
    elif await user_service.get_by_login(username):
        error = "Пользователь с таким логином уже существует"

    if error:
        return request.app.state.templates.TemplateResponse(
            "register.html",
            {"request": request, "error": error, "title": "Регистрация", "user": None},
        )

    hashed_password = hash_password(password)
    await user_service.create(username, hashed_password)
    # commit внутри сервиса или здесь
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# ----------------------
# Вход
# ----------------------
@router.get("/login")
async def login_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "login.html",
        {"request": request, "error": None, "title": "Вход", "user": None},
    )


@router.post("/login")
async def login_post(
    request: Request,
    login: str = Form(...),
    password: str = Form(...),
    user_service: UserServiceDep = Depends(),
):
    user = await user_service.get_by_login(login)
    if not user or not verify_password(password, user.hashed_password):
        return request.app.state.templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Неверный логин или пароль",
                "title": "Вход",
                "user": None,
            },
        )

    # TODO: установить сессию/куки
    return RedirectResponse(
        url=f"/user/{user.id}", status_code=status.HTTP_303_SEE_OTHER
    )


# ----------------------
# Профиль пользователя
# ----------------------
@router.get("/user/{user_id}")
async def user_profile(
    request: Request, user_id: int, user_service: UserServiceDep = Depends()
):
    user = await user_service.get_by_id(user_id)
    if not user:
        return request.app.state.templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "code": 404,
                "message": "Пользователь не найден",
                "user": None,
            },
            status_code=404,
        )
    return request.app.state.templates.TemplateResponse(
        "profile.html",
        {"request": request, "user": user, "title": f"Профиль {user.login}"},
    )


# ----------------------
# Админка
# ----------------------
@router.get("/admin")
async def admin_page(request: Request, role_service: RoleServiceDep = Depends()):
    admin_role = await role_service.get_by_name("admin")
    users = admin_role.users if admin_role else []
    return request.app.state.templates.TemplateResponse(
        "admin.html",
        {"request": request, "users": users, "title": "Админка", "user": None},
    )
