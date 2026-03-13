import json
from datetime import datetime
from typing import List, Dict, Optional
from services.database import async_session, CacheRepository
from config import settings


async def get_cached(key: str) -> Optional[Dict]:
    async with async_session() as session:
        cache_repo = CacheRepository(session)
        data = await cache_repo.get(key)
        if data:
            return json.loads(data)
    return None


async def set_cached(key: str, data: Dict, ttl: int = None):
    async with async_session() as session:
        cache_repo = CacheRepository(session)
        await cache_repo.set(key, json.dumps(data, ensure_ascii=False), ttl or settings.CACHE_TTL)


def format_balance(amount: float) -> str:
    return f"${amount:.2f}"


def format_datetime(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")


def format_phone(phone: str) -> str:
    if phone.startswith("7") and len(phone) == 11:
        return f"+7 ({phone[1:4]}) {phone[4:7]}-{phone[7:9]}-{phone[9:11]}"
    return f"+{phone}"


def get_status_text(status: str) -> str:
    statuses = {
        "waiting": "⏳ Ожидание SMS",
        "received": "✅ SMS получена",
        "completed": "✔️ Завершена",
        "cancelled": "❌ Отменена",
        "expired": "⌛ Истекла"
    }
    return statuses.get(status, status)


def paginate(items: list, page: int, per_page: int) -> tuple:
    total = len(items)
    total_pages = (total + per_page - 1) // per_page
    start = page * per_page
    end = start + per_page
    return items[start:end], total_pages


async def cleanup_cache():
    async with async_session() as session:
        cache_repo = CacheRepository(session)
        await cache_repo.delete_expired()
