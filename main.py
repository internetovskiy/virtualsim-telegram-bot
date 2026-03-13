import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from config import settings
from services.database import init_db
from services.virtualsim import virtualsim
from services.cryptobot import cryptobot
from middlewares.throttling import ThrottlingMiddleware
from middlewares.ban_check import BanCheckMiddleware
from handlers import start, balance, services, activations, admin
from utils.helpers import cleanup_cache
from utils.logger import setup_logging
import logging

setup_logging()
logger = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    await init_db()
    logger.info("Database initialized")

    me = await bot.get_me()
    logger.info(f"Bot started: @{me.username} (id={me.id})")

    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "✅ Бот запущен и готов к работе.")
        except Exception:
            pass


async def on_shutdown(bot: Bot):
    await virtualsim.close()
    await cryptobot.close()
    logger.info("Connections closed")

    for admin_id in settings.ADMIN_IDS:
        try:
            await bot.send_message(admin_id, "⚠️ Бот остановлен.")
        except Exception:
            pass


async def cache_cleanup_task():
    while True:
        await asyncio.sleep(3600)
        try:
            await cleanup_cache()
            logger.info("Cache cleanup done")
        except Exception as e:
            logger.error(f"Cache cleanup error: {e}")


async def main():
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(ThrottlingMiddleware(rate=0.5))
    dp.callback_query.middleware(ThrottlingMiddleware(rate=0.3))
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())

    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(balance.router)
    dp.include_router(services.router)
    dp.include_router(activations.router)

    await on_startup(bot)
    asyncio.create_task(cache_cleanup_task())

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown(bot)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
