from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.database import async_session, UserRepository, PaymentRepository
from services.cryptobot import cryptobot
from keyboards.inline import (
    main_menu_kb, back_to_menu_kb, deposit_amounts_kb,
    deposit_currency_kb, check_payment_kb
)
from keyboards.reply import cancel_kb, remove_kb
from config import settings

router = Router()


class DepositState(StatesGroup):
    waiting_amount = State()


@router.callback_query(F.data == "balance")
async def cb_balance(callback: CallbackQuery):
    async with async_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_telegram_id(callback.from_user.id)
    
    if not user:
        await callback.answer("Ошибка получения данных", show_alert=True)
        return
    
    async with async_session() as session:
        pay_repo = PaymentRepository(session)
        payments = await pay_repo.get_user_payments(user.id, limit=3)
    
    text = (
        f"💰 <b>Баланс</b>\n\n"
        f"Текущий баланс: <b>${user.balance:.2f}</b>\n"
        f"Всего потрачено: <b>${user.total_spent:.2f}</b>\n\n"
    )
    
    if payments:
        text += "📋 <b>Последние пополнения:</b>\n"
        for p in payments:
            status = "✅" if p.status == "paid" else "⏳"
            text += f"{status} ${p.amount:.2f} {p.currency} — {p.created_at.strftime('%d.%m.%Y')}\n"
    
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
        InlineKeyboardButton(text="◀️ Меню", callback_data="main_menu")
    )
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "deposit")
async def cb_deposit(callback: CallbackQuery):
    text = (
        "💳 <b>Пополнение баланса</b>\n\n"
        "Выберите сумму пополнения:"
    )
    await callback.message.edit_text(text, reply_markup=deposit_amounts_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("dep_amount_"))
async def cb_deposit_amount(callback: CallbackQuery):
    amount = float(callback.data.split("_")[2])
    text = (
        f"💳 <b>Пополнение на ${amount:.2f}</b>\n\n"
        f"Выберите криптовалюту для оплаты:"
    )
    await callback.message.edit_text(text, reply_markup=deposit_currency_kb(amount), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "dep_custom")
async def cb_deposit_custom(callback: CallbackQuery, state: FSMContext):
    await state.set_state(DepositState.waiting_amount)
    text = (
        f"✏️ Введите сумму пополнения в USD\n"
        f"Минимум: ${settings.MIN_DEPOSIT}, Максимум: ${settings.MAX_DEPOSIT}"
    )
    await callback.message.answer(text, reply_markup=cancel_kb())
    await callback.answer()


@router.message(DepositState.waiting_amount)
async def process_custom_amount(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Отменено", reply_markup=remove_kb())
        return
    
    try:
        amount = float(message.text.replace(",", "."))
        if amount < settings.MIN_DEPOSIT or amount > settings.MAX_DEPOSIT:
            await message.answer(f"⚠️ Сумма должна быть от ${settings.MIN_DEPOSIT} до ${settings.MAX_DEPOSIT}")
            return
    except ValueError:
        await message.answer("⚠️ Введите корректное число")
        return
    
    await state.clear()
    await message.answer("Выберите криптовалюту:", reply_markup=remove_kb())
    
    from aiogram.types import InlineKeyboardMarkup
    kb = deposit_currency_kb(amount)
    await message.answer(f"💳 Пополнение на <b>${amount:.2f}</b>", reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("dep_pay_"))
async def cb_create_invoice(callback: CallbackQuery):
    parts = callback.data.split("_")
    amount = float(parts[2])
    currency = parts[3]
    
    await callback.answer("⏳ Создаём счёт...", show_alert=False)
    
    try:
        payload = f"uid_{callback.from_user.id}_amt_{amount}"
        result = await cryptobot.create_invoice(amount, currency, payload)
        
        if not result.get("ok"):
            error = result.get("error", {}).get("name", "Неизвестная ошибка")
            await callback.message.edit_text(
                f"❌ Ошибка создания счёта: {error}",
                reply_markup=back_to_menu_kb()
            )
            return
        
        invoice = result["result"]
        invoice_id = str(invoice["invoice_id"])
        pay_url = invoice["pay_url"]
        
        async with async_session() as session:
            user_repo = UserRepository(session)
            user = await user_repo.get_by_telegram_id(callback.from_user.id)
            if user:
                pay_repo = PaymentRepository(session)
                await pay_repo.create(user.id, invoice_id, amount, currency)
        
        text = (
            f"💳 <b>Счёт создан</b>\n\n"
            f"Сумма: <b>${amount:.2f} {currency}</b>\n"
            f"ID счёта: <code>{invoice_id}</code>\n\n"
            f"Нажмите кнопку «Оплатить», затем проверьте оплату."
        )
        await callback.message.edit_text(
            text,
            reply_markup=check_payment_kb(invoice_id, pay_url),
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}",
            reply_markup=back_to_menu_kb()
        )


@router.callback_query(F.data.startswith("check_pay_"))
async def cb_check_payment(callback: CallbackQuery):
    invoice_id = callback.data.split("check_pay_")[1]
    
    await callback.answer("🔍 Проверяем оплату...", show_alert=False)
    
    async with async_session() as session:
        pay_repo = PaymentRepository(session)
        payment = await pay_repo.get_by_invoice_id(invoice_id)
    
    if not payment:
        await callback.answer("❌ Счёт не найден", show_alert=True)
        return
    
    if payment.status == "paid":
        await callback.answer("✅ Платёж уже зачислен!", show_alert=True)
        return
    
    try:
        invoice = await cryptobot.check_invoice(invoice_id)
        
        if not invoice:
            await callback.answer("❌ Счёт не найден в CryptoBot", show_alert=True)
            return
        
        if invoice["status"] == "paid":
            async with async_session() as session:
                pay_repo = PaymentRepository(session)
                paid = await pay_repo.mark_paid(invoice_id)
                
                if paid:
                    user_repo = UserRepository(session)
                    new_balance = await user_repo.update_balance(callback.from_user.id, payment.amount)
                    
                    text = (
                        f"✅ <b>Оплата подтверждена!</b>\n\n"
                        f"Зачислено: <b>${payment.amount:.2f}</b>\n"
                        f"Новый баланс: <b>${new_balance:.2f}</b>"
                    )
                    await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
                    return
        
        await callback.answer("⏳ Оплата ещё не поступила. Попробуйте через несколько секунд.", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка проверки: {str(e)}", show_alert=True)


@router.callback_query(F.data == "history")
async def cb_history(callback: CallbackQuery):
    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)
    
    if not user:
        await callback.answer("Ошибка", show_alert=True)
        return
    
    async with async_session() as session:
        act_repo = __import__('services.database', fromlist=['ActivationRepository']).ActivationRepository(session)
        activations = await act_repo.get_user_activations(user.id, limit=10)
    
    if not activations:
        text = "📊 <b>История</b>\n\nУ вас пока нет активаций."
    else:
        text = "📊 <b>История активаций</b>\n\n"
        for act in activations:
            status_icon = "✅" if act.status == "received" else "✔️" if act.status == "completed" else "❌" if act.status == "cancelled" else "⏳"
            text += (
                f"{status_icon} <b>{act.service_name}</b> | {act.country_name}\n"
                f"📱 <code>{act.phone_number}</code>\n"
                f"💰 ${act.cost:.2f} | {act.created_at.strftime('%d.%m %H:%M')}\n"
            )
            if act.sms_code:
                text += f"📩 {act.sms_code}\n"
            text += "\n"
    
    await callback.message.edit_text(text, reply_markup=back_to_menu_kb(), parse_mode="HTML")
    await callback.answer()
