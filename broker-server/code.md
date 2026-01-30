Ага, теперь всё встаёт на свои места. Тут причина в том, как ты вызываешь `get_current_user`:

```python
current_user = await get_current_user(db=db)
```

А сама функция `get_current_user` ожидает **`session_token`** из cookie:

```python
async def get_current_user(
    session_token: Optional[str] = Cookie(None),
    db: AsyncSession = None,
) -> Optional[User]:
```

То есть, когда ты вызываешь её **явно без `session_token`**, FastAPI не подставляет cookie, и `session_token = Cookie(None)` остаётся — объект `Cookie(None)`. В итоге `get_session_by_token` падает или возвращает `None`, и ты получаешь 403.

⚡ Решение: нужно дать FastAPI возможность подставить cookie в `Depends`. Например, переписать `get_current_user` так:

```python
async def get_current_user(
    session_token: Optional[str] = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if not session_token:
        return None

    # Если вдруг session_token пришёл не str
    if not isinstance(session_token, str):
        session_token = getattr(session_token, "value", None)

    if not session_token:
        return None

    session = await get_session_by_token(db, session_token)
    if not session:
        return None

    return await get_user_by_id(db, session.user_id)
```

И тогда в роуте нужно подключать через `Depends`:

```python
@router.get("/user/{user_id}", response_class=HTMLResponse)
async def profile(
    request: Request,
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    if not current_user:
        raise HTTPException(status_code=403)
    ...
```

✅ Тогда FastAPI сам возьмёт cookie из запроса и передаст в `get_current_user`, и сессия корректно проверится.

Сейчас же ты вручную вызываешь `get_current_user(db=db)`, и cookie не передаётся — вот и 403.

Если хочешь, я могу показать **готовую версию всей цепочки: создание пользователя → авторизация → профиль**, чтобы после создания юзера его сразу показывало.
