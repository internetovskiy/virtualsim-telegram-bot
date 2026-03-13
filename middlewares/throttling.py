from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable
from collections import defaultdict
import time


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate: float = 0.5):
        self.rate = rate
        self.user_timestamps: Dict[int, float] = defaultdict(float)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        
        if isinstance(event, Message):
            user_id = event.from_user.id
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id
        
        if user_id:
            now = time.time()
            last = self.user_timestamps[user_id]
            if now - last < self.rate:
                if isinstance(event, CallbackQuery):
                    await event.answer("⚠️ Не так быстро!", show_alert=False)
                return
            self.user_timestamps[user_id] = now
        
        return await handler(event, data)
