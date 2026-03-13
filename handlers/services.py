from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from services.virtualsim import virtualsim
from services.database import async_session, UserRepository
from keyboards.inline import (
    services_kb, countries_kb, confirm_order_kb,
    back_to_menu_kb, popular_services_kb, search_results_kb,
)
from utils.helpers import get_cached, set_cached
from config import settings

router = Router()

POPULAR_CODES = [
    "tg", "wa", "ig", "fb", "go", "tw", "ds", "vi", "oi",
    "vk", "wb", "ya", "ma", "me", "dt", "ot", "lf", "sn",
]


class SearchState(StatesGroup):
    waiting_query = State()
    waiting_country_query = State()


async def get_services_cached() -> list:
    cached = await get_cached("services_list")
    if cached:
        return cached

    result = await virtualsim.get_services()
    services = []

    if isinstance(result, dict) and "services" in result:
        raw = result["services"]
        if isinstance(raw, list):
            for s in raw:
                if isinstance(s, dict) and s.get("code"):
                    services.append({
                        "code": s["code"],
                        "name": s.get("name") or s["code"],
                    })

    services.sort(key=lambda x: (x.get("name") or "").lower())
    await set_cached("services_list", services, settings.CACHE_TTL)
    return services


async def get_countries_with_prices(service_code: str) -> list:
    cache_key = f"countries_{service_code}"
    cached = await get_cached(cache_key)
    if cached:
        return cached

    countries_result = await virtualsim.get_countries()
    prices_result = await virtualsim.get_prices(service=service_code)

    countries_map = {}
    if isinstance(countries_result, dict) and "countries" in countries_result:
        for c in countries_result["countries"]:
            countries_map[str(c["id"])] = c.get("eng") or c.get("rus") or f"ID {c['id']}"

    result = []
    if isinstance(prices_result, dict):
        for country_id_str, services_data in prices_result.items():
            if country_id_str in ("error",):
                continue
            if isinstance(services_data, dict) and service_code in services_data:
                data = services_data[service_code]
                country_name = countries_map.get(country_id_str, f"Country {country_id_str}")
                count = int(data.get("count") or 0)
                cost = float(data.get("cost") or 0)
                if count > 0 and cost > 0:
                    result.append({
                        "id": int(country_id_str),
                        "name": country_name,
                        "price": cost,
                        "count": count,
                    })

    result.sort(key=lambda x: x["price"])
    await set_cached(cache_key, result, settings.CACHE_TTL)
    return result

@router.callback_query(F.data == "buy_number")
async def cb_buy_number(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()

    services = await get_services_cached()
    if not services:
        await callback.message.edit_text(
            "❌ Не удалось загрузить список сервисов",
            reply_markup=back_to_menu_kb(),
        )
        return

    popular = [s for s in services if s["code"] in POPULAR_CODES]
    popular.sort(key=lambda s: POPULAR_CODES.index(s["code"]))

    text = (
        f"📱 <b>Выберите сервис</b>\n\n"
        f"⭐ Популярные сервисы ниже.\n"
        f"Всего доступно: <b>{len(services)}</b>\n\n"
        f"Нажмите 🔍 <b>Поиск</b>, чтобы найти нужный."
    )
    await callback.message.edit_text(
        text,
        reply_markup=popular_services_kb(popular),
        parse_mode="HTML",
    )

@router.callback_query(F.data == "svc_search")
async def cb_search_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SearchState.waiting_query)
    await callback.message.edit_text(
        "🔍 <b>Поиск сервиса</b>\n\n"
        "Введите название сервиса (например: <i>Telegram</i>, <i>WhatsApp</i>, <i>Google</i>):",
        parse_mode="HTML",
    )


@router.message(SearchState.waiting_query)
async def process_search_query(message: Message, state: FSMContext):
    query = (message.text or "").strip().lower()
    if not query:
        await message.answer("⚠️ Введите название сервиса.")
        return

    await state.clear()

    services = await get_services_cached()
    matches = [
        s for s in services
        if query in (s.get("name") or "").lower() or query in (s.get("code") or "").lower()
    ]

    if not matches:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔍 Искать снова", callback_data="svc_search"),
            InlineKeyboardButton(text="📋 Все сервисы", callback_data="svc_all_page_0"),
        )
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="buy_number"))
        await message.answer(
            f"😔 По запросу «<b>{message.text}</b>» ничего не найдено.\n\n"
            f"Попробуйте другое название или откройте полный список.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        return

    await state.update_data(search_query=query, search_results=[s["code"] for s in matches])

    text = f"🔍 Результаты поиска: «<b>{message.text}</b>» — найдено: <b>{len(matches)}</b>"
    await message.answer(
        text,
        reply_markup=search_results_kb(matches, page=0),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("svc_search_page_"))
async def cb_search_results_page(callback: CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[3])
    data = await state.get_data()
    codes = data.get("search_results") or []

    services = await get_services_cached()
    matches = [s for s in services if s["code"] in codes] if codes else services

    await callback.message.edit_reply_markup(reply_markup=search_results_kb(matches, page))
    await callback.answer()

@router.callback_query(F.data.startswith("svc_all_page_"))
async def cb_all_services_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[3])
    services = await get_services_cached()

    text = f"📋 <b>Все сервисы</b> ({len(services)})"
    await callback.message.edit_text(
        text,
        reply_markup=services_kb(services, page),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("svc_page_"))
async def cb_services_page(callback: CallbackQuery):
    page = int(callback.data.split("_")[2])
    services = await get_services_cached()
    await callback.message.edit_reply_markup(reply_markup=services_kb(services, page))
    await callback.answer()

@router.callback_query(F.data.startswith("svc_") & ~F.data.startswith("svc_page_") & ~F.data.startswith("svc_search") & ~F.data.startswith("svc_all_"))
async def cb_service_selected(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    service_code = callback.data[4:]
    await callback.answer("⏳ Загружаем страны...")

    try:
        countries = await get_countries_with_prices(service_code)

        if not countries:
            await callback.answer("❌ Нет доступных номеров для этого сервиса", show_alert=True)
            return

        services = await get_services_cached()
        service_name = next((s["name"] for s in services if s["code"] == service_code), service_code)

        text = (
            f"🌍 <b>Выберите страну</b>\n"
            f"Сервис: <b>{service_name}</b>\n\n"
            f"Доступно стран: {len(countries)}"
        )
        await callback.message.edit_text(
            text,
            reply_markup=countries_kb(countries, service_code, 0),
            parse_mode="HTML",
        )
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка: {str(e)}", reply_markup=back_to_menu_kb())

@router.callback_query(F.data.startswith("cnt_page_"))
async def cb_countries_page(callback: CallbackQuery):
    parts = callback.data.split("_")
    service_code = parts[2]
    page = int(parts[3])

    countries = await get_countries_with_prices(service_code)
    await callback.message.edit_reply_markup(
        reply_markup=countries_kb(countries, service_code, page),
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cnt_search_"))
async def cb_country_search_start(callback: CallbackQuery, state: FSMContext):
    service_code = callback.data[len("cnt_search_"):]
    await callback.answer()
    await state.set_state(SearchState.waiting_country_query)
    await state.update_data(country_search_svc=service_code)
    await callback.message.edit_text(
        "🔍 <b>Поиск страны</b>\n\n"
        "Введите название страны (например: <i>Russia</i>, <i>USA</i>, <i>Germany</i>):",
        parse_mode="HTML",
    )


@router.message(SearchState.waiting_country_query)
async def process_country_search(message: Message, state: FSMContext):
    query = (message.text or "").strip().lower()
    if not query:
        await message.answer("⚠️ Введите название страны.")
        return

    data = await state.get_data()
    service_code = data.get("country_search_svc", "")
    await state.clear()

    countries = await get_countries_with_prices(service_code)
    matches = [c for c in countries if query in (c.get("name") or "").lower()]

    services = await get_services_cached()
    service_name = next((s["name"] for s in services if s["code"] == service_code), service_code)

    if not matches:
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        from aiogram.types import InlineKeyboardButton
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="🔍 Искать снова", callback_data=f"cnt_search_{service_code}"),
            InlineKeyboardButton(text="📋 Все страны", callback_data=f"svc_{service_code}"),
        )
        builder.row(InlineKeyboardButton(text="◀️ К сервисам", callback_data="buy_number"))
        await message.answer(
            f"😔 По запросу «<b>{message.text}</b>» ничего не найдено.\n"
            f"Сервис: <b>{service_name}</b>\n\n"
            f"Попробуйте другое название.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        return

    await state.update_data(
        cnt_search_results=[c["id"] for c in matches],
        country_search_svc=service_code,
    )

    from keyboards.inline import country_search_results_kb
    text = (
        f"🔍 Результаты: «<b>{message.text}</b>»\n"
        f"Сервис: <b>{service_name}</b> — найдено стран: <b>{len(matches)}</b>"
    )
    await message.answer(
        text,
        reply_markup=country_search_results_kb(matches, service_code, page=0),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("cnt_spage_"))
async def cb_country_search_page(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    service_code = parts[2]
    page = int(parts[3])

    data = await state.get_data()
    ids = data.get("cnt_search_results") or []

    countries = await get_countries_with_prices(service_code)
    matches = [c for c in countries if c["id"] in ids] if ids else countries

    from keyboards.inline import country_search_results_kb
    await callback.message.edit_reply_markup(
        reply_markup=country_search_results_kb(matches, service_code, page),
    )
    await callback.answer()

@router.callback_query(F.data.startswith("cnt_") & ~F.data.startswith("cnt_page_") & ~F.data.startswith("cnt_search_") & ~F.data.startswith("cnt_spage_"))
async def cb_country_selected(callback: CallbackQuery):
    if callback.data.endswith("_back"):
        service_code = callback.data.split("_")[1]
        await callback.answer()
        services = await get_services_cached()
        countries = await get_countries_with_prices(service_code)
        service_name = next((s["name"] for s in services if s["code"] == service_code), service_code)
        text = (
            f"🌍 <b>Выберите страну</b>\n"
            f"Сервис: <b>{service_name}</b>\n\n"
            f"Доступно стран: {len(countries)}"
        )
        await callback.message.edit_text(
            text,
            reply_markup=countries_kb(countries, service_code, 0),
            parse_mode="HTML",
        )
        return

    parts = callback.data[4:].split("_")
    service_code = parts[0]
    country_id = int(parts[1])

    services = await get_services_cached()
    countries = await get_countries_with_prices(service_code)

    service_name = next((s["name"] for s in services if s["code"] == service_code), service_code)
    country = next((c for c in countries if c["id"] == country_id), None)

    if not country:
        await callback.answer("❌ Страна не найдена", show_alert=True)
        return

    async with async_session() as session:
        user_repo = UserRepository(session)
        user = await user_repo.get_by_telegram_id(callback.from_user.id)

    balance = user.balance if user else 0.0
    cost = country["price"]

    text = (
        f"🛒 <b>Подтверждение заказа</b>\n\n"
        f"📱 Сервис: <b>{service_name}</b>\n"
        f"🌍 Страна: <b>{country['name']}</b>\n"
        f"💰 Стоимость: <b>${cost:.2f}</b>\n"
        f"📦 Доступно: <b>{country['count']}</b> номеров\n\n"
        f"💳 Ваш баланс: <b>${balance:.2f}</b>\n"
    )

    if balance < cost:
        text += f"\n❌ <b>Недостаточно средств!</b>\nНужно ещё: ${cost - balance:.2f}"
        from aiogram.types import InlineKeyboardButton
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
            InlineKeyboardButton(text="◀️ Назад", callback_data="buy_number"),
        )
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await callback.message.edit_text(
            text,
            reply_markup=confirm_order_kb(service_code, country_id),
            parse_mode="HTML",
        )

    await callback.answer()
