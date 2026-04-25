from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy import select
from services.database import async_session, UserRepository, ActivationRepository, PaymentRepository, User
from services.virtualsim import virtualsim
from keyboards.inline import admin_kb
from keyboards.reply import cancel_kb, remove_kb
from config import settings
import asyncio
import logging

router = Router()
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


class BroadcastState(StatesGroup):
    waiting_message = State()


class AdminBalanceState(StatesGroup):
    waiting_user_id = State()
    waiting_amount = State()


class BanState(StatesGroup):
    waiting_user_id = State()


class UnbanState(StatesGroup):
    waiting_user_id = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛡️ <b>Панель администратора</b>", reply_markup=admin_kb(), parse_mode="HTML")


@router.message(Command("user"))
async def cmd_user_info(message: Message):
    if not is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("Использование: /user <telegram_id>")
        return

    try:
        target_id = int(args[1])
    except ValueError:
        await message.answer("❌ Неверный ID")
        return

    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(target_id)

    if not user:
        await message.answer("❌ Пользователь не найден")
        return

    async with async_session() as session:
        act_repo = ActivationRepository(session)
        activations = await act_repo.get_user_activations(user.id, limit=5)
        pay_repo = PaymentRepository(session)
        payments = await pay_repo.get_user_payments(user.id, limit=3)

    username = f"@{user.username}" if user.username else "—"
    ban_status = "🚫 Заблокирован" if user.is_banned else "✅ Активен"

    text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"ID: <code>{user.telegram_id}</code>\n"
        f"Имя: {user.full_name}\n"
        f"Username: {username}\n"
        f"Статус: {ban_status}\n"
        f"Баланс: <b>${user.balance:.2f}</b>\n"
        f"Потрачено: <b>${user.total_spent:.2f}</b>\n"
        f"Регистрация: {user.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    )

    if activations:
        text += "\n<b>Последние активации:</b>\n"
        for act in activations:
            text += f"• {act.service_name} | {act.country_name} | ${act.cost:.2f} | {act.status}\n"

    if payments:
        text += "\n<b>Последние пополнения:</b>\n"
        for pay in payments:
            status_icon = "✅" if pay.status == "paid" else "⏳"
            text += f"{status_icon} ${pay.amount:.2f} {pay.currency} | {pay.created_at.strftime('%d.%m.%Y')}\n"

    builder = InlineKeyboardBuilder()
    if user.is_banned:
        builder.button(text="✅ Разбанить", callback_data=f"admin_unban_direct_{target_id}")
    else:
        builder.button(text="🚫 Забанить", callback_data=f"admin_ban_direct_{target_id}")
    builder.button(text="➕ Пополнить", callback_data=f"admin_topup_direct_{target_id}")

    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_ban_direct_"))
async def cb_ban_direct(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    target_id = int(callback.data.split("_")[-1])

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_banned = True
            await session.commit()

    await callback.answer(f"🚫 Пользователь {target_id} заблокирован", show_alert=True)

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Разбанить", callback_data=f"admin_unban_direct_{target_id}")
    builder.button(text="➕ Пополнить", callback_data=f"admin_topup_direct_{target_id}")
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

    try:
        await bot.send_message(target_id, "🚫 Ваш аккаунт был заблокирован администратором.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_unban_direct_"))
async def cb_unban_direct(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    target_id = int(callback.data.split("_")[-1])

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if user:
            user.is_banned = False
            await session.commit()

    await callback.answer(f"✅ Пользователь {target_id} разбанен", show_alert=True)

    builder = InlineKeyboardBuilder()
    builder.button(text="🚫 Забанить", callback_data=f"admin_ban_direct_{target_id}")
    builder.button(text="➕ Пополнить", callback_data=f"admin_topup_direct_{target_id}")
    await callback.message.edit_reply_markup(reply_markup=builder.as_markup())

    try:
        await bot.send_message(target_id, "✅ Ваш аккаунт разблокирован. Добро пожаловать обратно!")
    except Exception:
        pass


@router.callback_query(F.data.startswith("admin_topup_direct_"))
async def cb_topup_direct(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    target_id = int(callback.data.split("_")[-1])
    await state.set_state(AdminBalanceState.waiting_amount)
    await state.update_data(target_user_id=target_id)
    await callback.message.answer(
        f"Введите сумму для пополнения пользователя <code>{target_id}</code>:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        user_repo = UserRepository(session)
        users = await user_repo.get_all_users()

    total_users = len(users)
    total_balance = sum(u.balance for u in users)
    total_spent = sum(u.total_spent for u in users)
    banned = sum(1 for u in users if u.is_banned)

    try:
        api_balance = await virtualsim.get_balance()
        if api_balance.get("error"):
            api_bal_text = f"❌ {api_balance.get('error')}"
        else:
            api_bal_text = f"${float(api_balance.get('balance', 0)):.2f}"
    except Exception:
        api_bal_text = "❌ Ошибка"

    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{total_users}</b>\n"
        f"🚫 Заблокировано: <b>{banned}</b>\n"
        f"💰 Баланс пользователей: <b>${total_balance:.2f}</b>\n"
        f"💸 Всего потрачено: <b>${total_spent:.2f}</b>\n\n"
        f"🔑 Баланс VirtualSim API: <b>{api_bal_text}</b>"
    )

    await callback.message.edit_text(text, reply_markup=admin_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_balance")
async def cb_admin_api_balance(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    try:
        result = await virtualsim.get_balance()
        if result.get("error"):
            text = f"❌ <b>Ошибка API</b>\n{result.get('error')}"
        else:
            cur = result.get("currency", "USD")
            text = f"💰 <b>Баланс VirtualSim API</b>\n\n${float(result.get('balance', 0)):.2f} {cur}"
    except Exception as e:
        text = f"❌ Ошибка получения баланса: {str(e)}"

    await callback.message.edit_text(text, reply_markup=admin_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def cb_admin_users(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    async with async_session() as session:
        user_repo = UserRepository(session)
        users = await user_repo.get_all_users()

    if not users:
        text = "👥 Пользователей нет"
    else:
        text = f"👥 <b>Пользователи ({len(users)})</b>\n\n"
        for user in users[-15:]:
            username = f"@{user.username}" if user.username else "—"
            ban_icon = "🚫" if user.is_banned else "✅"
            text += f"{ban_icon} <code>{user.telegram_id}</code> {user.full_name} {username} | <b>${user.balance:.2f}</b>\n"
        if len(users) > 15:
            text += f"\n... и ещё {len(users) - 15}"

    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="➕ Пополнить баланс", callback_data="admin_add_balance"),
        InlineKeyboardButton(text="🚫 Забанить", callback_data="admin_ban_user")
    )
    builder.row(
        InlineKeyboardButton(text="✅ Разбанить", callback_data="admin_unban_user"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")
    )

    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_ban_user")
async def cb_admin_ban_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(BanState.waiting_user_id)
    await callback.message.answer("Введите Telegram ID пользователя для блокировки:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(BanState.waiting_user_id)
async def admin_ban_user(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=remove_kb())
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("❌ Пользователь не найден", reply_markup=remove_kb())
            await state.clear()
            return
        user.is_banned = True
        await session.commit()

    await state.clear()
    await message.answer(
        f"🚫 Пользователь <code>{target_id}</code> заблокирован.",
        reply_markup=remove_kb(),
        parse_mode="HTML"
    )

    try:
        await bot.send_message(target_id, "🚫 Ваш аккаунт был заблокирован администратором.")
    except Exception:
        pass


@router.callback_query(F.data == "admin_unban_user")
async def cb_admin_unban_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(UnbanState.waiting_user_id)
    await callback.message.answer("Введите Telegram ID пользователя для разблокировки:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(UnbanState.waiting_user_id)
async def admin_unban_user(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=remove_kb())
        return

    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID")
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == target_id))
        user = result.scalar_one_or_none()
        if not user:
            await message.answer("❌ Пользователь не найден", reply_markup=remove_kb())
            await state.clear()
            return
        user.is_banned = False
        await session.commit()

    await state.clear()
    await message.answer(
        f"✅ Пользователь <code>{target_id}</code> разблокирован.",
        reply_markup=remove_kb(),
        parse_mode="HTML"
    )

    try:
        await bot.send_message(target_id, "✅ Ваш аккаунт разблокирован. Добро пожаловать обратно!")
    except Exception:
        pass


@router.callback_query(F.data == "admin_panel")
async def cb_admin_panel(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    await callback.message.edit_text("🛡️ <b>Панель администратора</b>", reply_markup=admin_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_add_balance")
async def cb_admin_add_balance(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(AdminBalanceState.waiting_user_id)
    await callback.message.answer("Введите Telegram ID пользователя:", reply_markup=cancel_kb())
    await callback.answer()


@router.message(AdminBalanceState.waiting_user_id)
async def admin_get_user_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=remove_kb())
        return

    try:
        user_id = int(message.text.strip())
        await state.update_data(target_user_id=user_id)
        await state.set_state(AdminBalanceState.waiting_amount)
        await message.answer("Введите сумму (+ пополнение, - списание):")
    except ValueError:
        await message.answer("❌ Введите корректный числовой ID")


@router.message(AdminBalanceState.waiting_amount)
async def admin_add_balance_amount(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=remove_kb())
        return

    try:
        amount = float(message.text.replace(",", "."))
        data = await state.get_data()
        target_user_id = data["target_user_id"]

        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(target_user_id)
            if not user:
                await message.answer("❌ Пользователь не найден", reply_markup=remove_kb())
                await state.clear()
                return
            new_balance = await user_repo.update_balance(target_user_id, amount)

        await state.clear()
        action = "Пополнен" if amount > 0 else "Списан"
        await message.answer(
            f"✅ {action} баланс пользователя <code>{target_user_id}</code>\n"
            f"Сумма: <b>${amount:+.2f}</b>\nНовый баланс: <b>${new_balance:.2f}</b>",
            reply_markup=remove_kb(),
            parse_mode="HTML"
        )
    except ValueError:
        await message.answer("❌ Введите корректное число")


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return

    await state.set_state(BroadcastState.waiting_message)
    await callback.message.answer(
        "📢 Введите сообщение для рассылки.\nПоддерживается HTML-форматирование.",
        reply_markup=cancel_kb()
    )
    await callback.answer()


@router.message(BroadcastState.waiting_message)
async def admin_do_broadcast(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return

    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=remove_kb())
        return

    await state.clear()

    async with async_session() as session:
        user_repo = UserRepository(session)
        users = await user_repo.get_all_users()

    active_users = [u for u in users if not u.is_banned]
    sent = 0
    failed = 0

    progress_msg = await message.answer(
        f"📢 Рассылка... 0/{len(active_users)}",
        reply_markup=remove_kb()
    )

    for i, user in enumerate(active_users):
        try:
            await bot.send_message(
                user.telegram_id,
                f"📢 <b>Сообщение от администратора</b>\n\n{message.text}",
                parse_mode="HTML"
            )
            sent += 1
        except Exception as e:
            failed += 1
            logger.warning(f"Broadcast failed for {user.telegram_id}: {e}")

        if (i + 1) % 20 == 0:
            try:
                await progress_msg.edit_text(f"📢 Рассылка... {i + 1}/{len(active_users)}")
            except Exception:
                pass

        await asyncio.sleep(0.05)

    await progress_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"✉️ Отправлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>",
        parse_mode="HTML"
    )
