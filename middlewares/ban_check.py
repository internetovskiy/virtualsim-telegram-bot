from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
from services.database import async_session, UserRepository


class BanCheckMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = None

        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user:
            async with async_session() as session:
                repo = UserRepository(session)
                db_user = await repo.get_by_telegram_id(user.id)
                if db_user and db_user.is_banned:
                    if isinstance(event, Message):
                        await event.answer("🚫 Вы заблокированы в этом боте.")
                    elif isinstance(event, CallbackQuery):
                        await event.answer("🚫 Вы заблокированы.", show_alert=True)
                    return

        return await handler(event, data)
