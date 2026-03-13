from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import List, Dict


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📱 Купить номер", callback_data="buy_number"),
        InlineKeyboardButton(text="⚡ Мои активации", callback_data="my_activations"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Баланс", callback_data="balance"),
        InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
    )
    builder.row(
        InlineKeyboardButton(text="📊 История", callback_data="history"),
        InlineKeyboardButton(text="ℹ️ Помощь", callback_data="help"),
    )
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Главное меню", callback_data="main_menu")
    return builder.as_markup()


def popular_services_kb(popular: List[Dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for svc in popular:
        name = svc.get("name") or svc["code"]
        builder.button(text=name, callback_data=f"svc_{svc['code']}")
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(text="🔍 Поиск", callback_data="svc_search"),
        InlineKeyboardButton(text="📋 Все сервисы", callback_data="svc_all_page_0"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))
    return builder.as_markup()


def search_results_kb(
    services: List[Dict], page: int = 0, per_page: int = 8
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    page_services = services[start:end]

    for svc in page_services:
        name = svc.get("name") or svc["code"]
        builder.button(text=name, callback_data=f"svc_{svc['code']}")
    builder.adjust(2)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"svc_search_page_{page - 1}"))
    total_pages = (len(services) + per_page - 1) // per_page
    if total_pages > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if end < len(services):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"svc_search_page_{page + 1}"))
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data="svc_search"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="buy_number"),
    )
    return builder.as_markup()


def services_kb(
    services: List[Dict], page: int = 0, per_page: int = 8
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    page_services = services[start:end]

    for service in page_services:
        name = service.get("name") or service["code"]
        builder.button(text=name, callback_data=f"svc_{service['code']}")
    builder.adjust(2)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"svc_page_{page - 1}"))
    total_pages = (len(services) + per_page - 1) // per_page
    nav_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if end < len(services):
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"svc_page_{page + 1}"))
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(text="🔍 Поиск", callback_data="svc_search"),
        InlineKeyboardButton(text="◀️ Назад", callback_data="buy_number"),
    )
    return builder.as_markup()


def countries_kb(
    countries: List[Dict], service_code: str, page: int = 0, per_page: int = 8
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    page_countries = countries[start:end]

    for country in page_countries:
        price = country.get("price", "?")
        count = country.get("count", 0)
        flag = _country_flag(country.get("name", ""))
        builder.button(
            text=f"{flag} {country['name']} — ${price:.2f} ({count})",
            callback_data=f"cnt_{service_code}_{country['id']}",
        )
    builder.adjust(1)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton(text="◀️", callback_data=f"cnt_page_{service_code}_{page - 1}")
        )
    total_pages = (len(countries) + per_page - 1) // per_page
    if total_pages > 1:
        nav_buttons.append(
            InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop")
        )
    if end < len(countries):
        nav_buttons.append(
            InlineKeyboardButton(text="▶️", callback_data=f"cnt_page_{service_code}_{page + 1}")
        )
    if nav_buttons:
        builder.row(*nav_buttons)

    builder.row(
        InlineKeyboardButton(text="🔍 Поиск страны", callback_data=f"cnt_search_{service_code}"),
        InlineKeyboardButton(text="◀️ К сервисам", callback_data="buy_number"),
    )
    return builder.as_markup()


def country_search_results_kb(
    countries: List[Dict], service_code: str, page: int = 0, per_page: int = 8
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    start = page * per_page
    end = start + per_page
    page_countries = countries[start:end]

    for country in page_countries:
        price = country.get("price", 0)
        count = country.get("count", 0)
        flag = _country_flag(country.get("name", ""))
        builder.button(
            text=f"{flag} {country['name']} — ${price:.2f} ({count})",
            callback_data=f"cnt_{service_code}_{country['id']}",
        )
    builder.adjust(1)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"cnt_spage_{service_code}_{page - 1}"))
    total_pages = (len(countries) + per_page - 1) // per_page
    if total_pages > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="noop"))
    if end < len(countries):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"cnt_spage_{service_code}_{page + 1}"))
    if nav:
        builder.row(*nav)

    builder.row(
        InlineKeyboardButton(text="🔍 Новый поиск", callback_data=f"cnt_search_{service_code}"),
        InlineKeyboardButton(text="◀️ Все страны", callback_data=f"svc_{service_code}"),
    )
    return builder.as_markup()


def _country_flag(name: str) -> str:
    flags = {
        "russia": "🇷🇺", "usa": "🇺🇸", "united states": "🇺🇸", "ukraine": "🇺🇦",
        "united kingdom": "🇬🇧", "england": "🇬🇧", "germany": "🇩🇪", "france": "🇫🇷",
        "spain": "🇪🇸", "italy": "🇮🇹", "china": "🇨🇳", "india": "🇮🇳",
        "brazil": "🇧🇷", "indonesia": "🇮🇩", "turkey": "🇹🇷", "netherlands": "🇳🇱",
        "poland": "🇵🇱", "canada": "🇨🇦", "australia": "🇦🇺", "japan": "🇯🇵",
        "south korea": "🇰🇷", "mexico": "🇲🇽", "philippines": "🇵🇭",
        "thailand": "🇹🇭", "vietnam": "🇻🇳", "malaysia": "🇲🇾", "kazakhstan": "🇰🇿",
        "romania": "🇷🇴", "colombia": "🇨🇴", "argentina": "🇦🇷", "nigeria": "🇳🇬",
        "kenya": "🇰🇪", "egypt": "🇪🇬", "morocco": "🇲🇦", "sweden": "🇸🇪",
        "portugal": "🇵🇹", "czech": "🇨🇿", "finland": "🇫🇮", "myanmar": "🇲🇲",
        "bangladesh": "🇧🇩", "pakistan": "🇵🇰", "hongkong": "🇭🇰", "hong kong": "🇭🇰",
        "cambodia": "🇰🇭", "laos": "🇱🇦", "nepal": "🇳🇵", "estonia": "🇪🇪",
        "latvia": "🇱🇻", "lithuania": "🇱🇹",
    }
    return flags.get(name.lower(), "🌍")



def confirm_order_kb(service_code: str, country_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Купить", callback_data=f"confirm_{service_code}_{country_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"cnt_{service_code}_{country_id}_back"),
    )
    return builder.as_markup()


def activation_control_kb(activation_id: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data=f"act_refresh_{activation_id}"),
        InlineKeyboardButton(text="📨 Новая SMS", callback_data=f"act_resend_{activation_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="✅ Завершить", callback_data=f"act_complete_{activation_id}"),
        InlineKeyboardButton(text="❌ Отменить", callback_data=f"act_cancel_{activation_id}"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Мои активации", callback_data="my_activations"))
    return builder.as_markup()


def deposit_amounts_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    amounts = [1, 5, 10, 25, 50, 100]
    for amount in amounts:
        builder.button(text=f"${amount}", callback_data=f"dep_amount_{amount}")
    builder.adjust(3)
    builder.row(InlineKeyboardButton(text="✏️ Другая сумма", callback_data="dep_custom"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))
    return builder.as_markup()


def deposit_currency_kb(amount: float) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    currencies = [("USDT", "💵 USDT")]
    for code, label in currencies:
        builder.button(text=label, callback_data=f"dep_pay_{amount}_{code}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="deposit"))
    return builder.as_markup()


def check_payment_kb(invoice_id: str, pay_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оплатить", url=pay_url))
    builder.row(InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_pay_{invoice_id}"))
    builder.row(InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu"))
    return builder.as_markup()

def activations_list_kb(activations: List) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for act in activations:
        status_icon = "⏳" if act.status == "waiting" else "✅" if act.status == "received" else "🔴"
        builder.button(
            text=f"{status_icon} {act.service_name} | {act.phone_number}",
            callback_data=f"act_view_{act.activation_id}",
        )
    builder.adjust(1)
    builder.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu"))
    return builder.as_markup()


def admin_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"),
        InlineKeyboardButton(text="💰 Баланс API", callback_data="admin_balance"),
    )
    builder.row(
        InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Главное меню", callback_data="main_menu"))
    return builder.as_markup()
