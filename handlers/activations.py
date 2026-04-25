from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from services.virtualsim import virtualsim
from services.database import async_session, UserRepository, ActivationRepository
from keyboards.inline import (
    activation_control_kb, activations_list_kb, back_to_menu_kb, main_menu_kb
)
from utils.helpers import get_cached, format_phone, get_status_text, apply_markup
import asyncio
import logging

router = Router()
logger = logging.getLogger(__name__)

_polling_tasks = {}


def _format_sms_message(activation, sms_code: str) -> str:
    return (
        f"✅ <b>SMS получена!</b>\n\n"
        f"📱 Сервис: <b>{activation.service_name}</b>\n"
        f"🌍 Страна: <b>{activation.country_name}</b>\n"
        f"📞 Номер: <code>{format_phone(activation.phone_number)}</code>\n"
        f"💰 Стоимость: <b>${activation.cost:.2f}</b>\n\n"
        f"📩 <b>SMS:</b>\n<code>{sms_code}</code>\n\n"
        f"👆 <i>Нажмите на код, чтобы скопировать</i>"
    )


def _format_activation_card(activation) -> str:
    status_text = get_status_text(activation.status)
    text = (
        f"📱 <b>{activation.service_name}</b>\n\n"
        f"📞 Номер: <code>{format_phone(activation.phone_number)}</code>\n"
        f"🌍 Страна: {activation.country_name}\n"
        f"💰 Стоимость: ${activation.cost:.2f}\n"
        f"📊 Статус: {status_text}\n"
        f"🕐 Создана: {activation.created_at.strftime('%d.%m.%Y %H:%M')}\n"
    )
    if activation.sms_code:
        text += (
            f"\n📩 <b>SMS:</b>\n<code>{activation.sms_code}</code>\n"
            f"👆 <i>Нажмите, чтобы скопировать</i>"
        )
    return text


async def poll_activation(
    bot: Bot, user_telegram_id: int, activation_id: str,
    message_id: int, chat_id: int,
):
    from config import settings
    import time

    start_time = time.time()

    while time.time() - start_time < settings.ACTIVATION_TIMEOUT:
        try:
            await asyncio.sleep(settings.ACTIVATION_POLL_INTERVAL)

            result = await virtualsim.get_status(activation_id)

            if not isinstance(result, dict):
                continue

            if result.get("error"):
                code = result.get("_http_status", 0)
                if code == 404:
                    break
                if code == 429:
                    await asyncio.sleep(8)
                continue

            sms_received = result.get("smsReceived", False)
            messages = result.get("messages") or []
            api_status = result.get("status", "")

            if api_status == "cancelled":
                async with async_session() as session:
                    act_repo = ActivationRepository(session)
                    await act_repo.update_status(activation_id, "cancelled")
                break

            sms_code = None
            if sms_received and messages:
                sms_code = messages[-1].get("text", "")

            if sms_code:
                async with async_session() as session:
                    act_repo = ActivationRepository(session)
                    activation = await act_repo.update_status(
                        activation_id, "received", sms_code,
                    )

                if activation:
                    text = _format_sms_message(activation, sms_code)
                    try:
                        await bot.edit_message_text(
                            text, chat_id=chat_id, message_id=message_id,
                            reply_markup=activation_control_kb(activation_id),
                            parse_mode="HTML",
                        )
                    except Exception:
                        await bot.send_message(
                            chat_id, text,
                            reply_markup=activation_control_kb(activation_id),
                            parse_mode="HTML",
                        )
                break

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Polling error for {activation_id}: {e}")
            await asyncio.sleep(10)

    _polling_tasks.pop(f"{user_telegram_id}_{activation_id}", None)


@router.callback_query(F.data.startswith("confirm_"))
async def cb_confirm_order(callback: CallbackQuery, bot: Bot):
    parts = callback.data[8:].split("_")
    service_code = parts[0]
    country_id = int(parts[1])

    await callback.answer("⏳ Оформляем заказ...")

    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)

    if not user:
        await callback.message.edit_text(
            "❌ Ошибка: пользователь не найден", reply_markup=back_to_menu_kb(),
        )
        return

    try:
        services_cached = await get_cached("services_list")
        service_name = service_code
        if services_cached:
            svc = next((s for s in services_cached if s["code"] == service_code), None)
            if svc:
                service_name = svc["name"]

        countries_cached = await get_cached(f"countries_{service_code}")
        country_name = f"Country {country_id}"
        cost = 0.0
        if countries_cached:
            country = next((c for c in countries_cached if c["id"] == country_id), None)
            if country:
                country_name = country["name"]
                cost = country["price"]

        if user.balance < cost:
            await callback.message.edit_text(
                f"❌ Недостаточно средств!\nБаланс: ${user.balance:.2f}, Нужно: ${cost:.2f}",
                reply_markup=back_to_menu_kb(),
            )
            return

        order = await virtualsim.order_number(service_code, country_id)

        if order.get("error") or "activationId" not in order:
            error_msg = (
                order.get("error")
                or order.get("message")
                or "Неизвестная ошибка"
            )
            await callback.message.edit_text(
                f"❌ Ошибка заказа: {error_msg}", reply_markup=back_to_menu_kb(),
            )
            return

        activation_id = str(order["activationId"])
        phone_number = order.get("phoneNumber") or order.get("number", "")
        api_cost = float(order.get("cost") or order.get("cost_with_markup") or cost)
        user_cost = max(cost, apply_markup(api_cost))

        async with async_session() as session:
            user_repo = UserRepository(session)
            await user_repo.update_balance(callback.from_user.id, -user_cost)

            act_repo = ActivationRepository(session)
            await act_repo.create(
                user.id, activation_id, service_code, service_name,
                country_id, country_name, phone_number, user_cost,
            )

        text = (
            f"✅ <b>Номер успешно куплен!</b>\n\n"
            f"📱 Сервис: <b>{service_name}</b>\n"
            f"🌍 Страна: <b>{country_name}</b>\n"
            f"📞 Номер: <code>{format_phone(phone_number)}</code>\n"
            f"💰 Списано: <b>${user_cost:.2f}</b>\n\n"
            f"⏳ <b>Ожидаем SMS...</b>\n"
            f"Код придёт автоматически в течение нескольких минут."
        )

        sent_msg = await callback.message.edit_text(
            text, reply_markup=activation_control_kb(activation_id), parse_mode="HTML",
        )

        task_key = f"{callback.from_user.id}_{activation_id}"
        task = asyncio.create_task(
            poll_activation(
                bot, callback.from_user.id, activation_id,
                sent_msg.message_id, callback.message.chat.id,
            )
        )
        _polling_tasks[task_key] = task

    except Exception as e:
        await callback.message.edit_text(
            f"❌ Ошибка: {str(e)}", reply_markup=back_to_menu_kb(),
        )


@router.callback_query(F.data == "my_activations")
async def cb_my_activations(callback: CallbackQuery):
    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)

    if not user:
        await callback.answer("Ошибка", show_alert=True)
        return

    async with async_session() as session:
        act_repo = ActivationRepository(session)
        activations = await act_repo.get_active_activations(user.id)

    if not activations:
        text = (
            "⚡ <b>Мои активации</b>\n\n"
            "У вас нет активных активаций.\n"
            "Купите номер для начала работы."
        )
        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="📱 Купить номер", callback_data="buy_number"),
            InlineKeyboardButton(text="◀️ Меню", callback_data="main_menu"),
        )
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        text = f"⚡ <b>Активные активации</b> ({len(activations)})\n\nВыберите активацию:"
        await callback.message.edit_text(
            text, reply_markup=activations_list_kb(activations), parse_mode="HTML",
        )

    await callback.answer()


@router.callback_query(F.data.startswith("act_view_"))
async def cb_view_activation(callback: CallbackQuery):
    activation_id = callback.data[9:]

    async with async_session() as session:
        act_repo = ActivationRepository(session)
        activation = await act_repo.get_by_activation_id(activation_id)

    if not activation:
        await callback.answer("❌ Активация не найдена", show_alert=True)
        return

    await callback.message.edit_text(
        _format_activation_card(activation),
        reply_markup=activation_control_kb(activation_id),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("act_refresh_"))
async def cb_refresh_activation(callback: CallbackQuery):
    activation_id = callback.data[12:]

    await callback.answer("🔄 Обновляем...")

    activation = None
    try:
        result = await virtualsim.get_status(activation_id)

        sms_code = None
        if isinstance(result, dict) and not result.get("error"):
            messages = result.get("messages") or []
            if messages:
                sms_code = messages[-1].get("text")

        async with async_session() as session:
            act_repo = ActivationRepository(session)
            activation = await act_repo.get_by_activation_id(activation_id)
            if sms_code and activation and activation.sms_code != sms_code:
                await act_repo.update_status(activation_id, "received", sms_code)
                activation.sms_code = sms_code
                activation.status = "received"

        if not activation:
            await callback.answer("❌ Активация не найдена", show_alert=True)
            return

        await callback.message.edit_text(
            _format_activation_card(activation),
            reply_markup=activation_control_kb(activation_id),
            parse_mode="HTML",
        )
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("act_resend_"))
async def cb_resend_sms(callback: CallbackQuery):
    activation_id = callback.data[11:]

    await callback.answer("📨 Запрашиваем новую SMS...")

    try:
        r = await virtualsim.set_status(activation_id, 3)
        if r.get("error"):
            await callback.answer(f"❌ {r.get('error')}", show_alert=True)
            return
        await callback.answer("✅ Запрос отправлен. Ожидайте новую SMS.", show_alert=True)
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("act_complete_"))
async def cb_complete_activation(callback: CallbackQuery):
    activation_id = callback.data[13:]

    try:
        r = await virtualsim.set_status(activation_id, 6)
        if r.get("error"):
            await callback.answer(f"❌ {r.get('error')}", show_alert=True)
            return

        async with async_session() as session:
            act_repo = ActivationRepository(session)
            await act_repo.update_status(activation_id, "completed")

        task_key = f"{callback.from_user.id}_{activation_id}"
        if task_key in _polling_tasks:
            _polling_tasks[task_key].cancel()
            del _polling_tasks[task_key]

        await callback.message.edit_text(
            "✔️ <b>Активация завершена!</b>\n\nСпасибо за использование сервиса.",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )
        await callback.answer("✅ Завершено")
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)


@router.callback_query(F.data.startswith("act_cancel_"))
async def cb_cancel_activation(callback: CallbackQuery):
    activation_id = callback.data[11:]

    try:
        r = await virtualsim.set_status(activation_id, 8)
        if r.get("error"):
            await callback.answer(f"❌ {r.get('error')}", show_alert=True)
            return

        async with async_session() as session:
            act_repo = ActivationRepository(session)
            activation = await act_repo.get_by_activation_id(activation_id)
            if activation and activation.status == "waiting":
                await act_repo.update_status(activation_id, "cancelled")
                user_repo = UserRepository(session)
                user = await user_repo.get_by_telegram_id(callback.from_user.id)
                if user:
                    await user_repo.update_balance(callback.from_user.id, activation.cost)

        task_key = f"{callback.from_user.id}_{activation_id}"
        if task_key in _polling_tasks:
            _polling_tasks[task_key].cancel()
            del _polling_tasks[task_key]

        await callback.message.edit_text(
            "❌ <b>Активация отменена</b>\n\nСредства возвращены на ваш баланс.",
            reply_markup=main_menu_kb(),
            parse_mode="HTML",
        )
        await callback.answer("✅ Отменено, средства возвращены")
    except Exception as e:
        await callback.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
