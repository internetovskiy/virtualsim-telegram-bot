from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from services.database import async_session, UserRepository
from keyboards.inline import main_menu_kb, back_to_menu_kb

router = Router()


async def ensure_user(telegram_id: int, username: str, full_name: str):
    async with async_session() as session:
        repo = UserRepository(session)
        return await repo.get_or_create(telegram_id, username, full_name)


@router.message(CommandStart())
async def cmd_start(message: Message):
    user = await ensure_user(
        message.from_user.id,
        message.from_user.username or "",
        message.from_user.full_name
    )
    
    text = (
        f"👋 Привет, <b>{message.from_user.first_name}</b>!\n\n"
        f"🤖 <b>VirtualSim Bot</b> — сервис для получения виртуальных номеров\n\n"
        f"📱 Поддерживается 180+ стран и тысячи сервисов\n"
        f"💰 Ваш баланс: <b>${user.balance:.2f}</b>\n\n"
        f"Выберите действие:"
    )
    await message.answer(text, reply_markup=main_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery):
    async with async_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(callback.from_user.id)
    
    balance = user.balance if user else 0.0
    text = (
        f"🏠 <b>Главное меню</b>\n\n"
        f"💰 Баланс: <b>${balance:.2f}</b>\n\n"
        f"Выберите действие:"
    )
    await callback.message.edit_text(text, reply_markup=main_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await callback.answer()


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery):
    text = (
        "ℹ️ <b>Помощь</b>\n\n"
        "📱 <b>Как купить номер:</b>\n"
        "1. Нажмите «Купить номер»\n"
        "2. Выберите сервис (Telegram, WhatsApp и др.)\n"
        "3. Выберите страну и тариф\n"
        "4. Подтвердите покупку\n"
        "5. Дождитесь SMS-кода\n\n"
        "💳 <b>Пополнение баланса:</b>\n"
        "Принимаем: USDT, TON, BTC, ETH через CryptoBot\n\n"
        "⚡ <b>Статусы активации:</b>\n"
        "⏳ Ожидание — ждём SMS\n"
        "✅ Получена — SMS пришла\n"
        "✔️ Завершена — активация закрыта\n"
        "❌ Отменена — средства возвращены\n\n"
        "🆘 Поддержка: @support"
    )
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()
