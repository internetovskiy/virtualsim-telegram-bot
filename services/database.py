from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, select, update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from config import settings

logger = logging.getLogger(__name__)


def _normalize_sqlite_url(url: str) -> str:
    """
    Ensure parent directory exists and use an absolute file path.
    Fixes sqlite3.OperationalError: unable to open database file on Windows/Linux
    when DATABASE_URL points at e.g. data/bot.db but ./data/ was never created;
    also avoids cwd surprises by resolving relative paths to absolute.
    """
    if "sqlite" not in url or "aiosqlite" not in url:
        return url
    low = url.lower()
    if ":memory:" in low or "mode=memory" in low:
        return url
    try:
        u = make_url(url)
    except Exception:
        return url
    drv = getattr(u, "drivername", "") or ""
    if not drv.startswith("sqlite"):
        return url
    path_part = u.database
    if path_part is None or str(path_part) in ("", ":memory:"):
        return url
    path_part = unquote(str(path_part))
    if path_part.lower().startswith("file:"):
        path_part = path_part[5:].lstrip("/")
    p = Path(path_part)
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    else:
        p = p.resolve()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("Could not create directory for database %s: %s", p, e)
        raise
    return f"sqlite+aiosqlite:///{p.as_posix()}"


DATABASE_URL = _normalize_sqlite_url(settings.DATABASE_URL)
logger.info("Database file: %s", DATABASE_URL.replace("sqlite+aiosqlite:///", "", 1))

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128))
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    total_spent: Mapped[float] = mapped_column(Float, default=0.0)


class Activation(Base):
    __tablename__ = "activations"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    activation_id: Mapped[str] = mapped_column(String(32), index=True)
    service: Mapped[str] = mapped_column(String(16))
    service_name: Mapped[str] = mapped_column(String(64))
    country_id: Mapped[int] = mapped_column(Integer)
    country_name: Mapped[str] = mapped_column(String(64))
    phone_number: Mapped[str] = mapped_column(String(32))
    cost: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="waiting")
    sms_code: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Payment(Base):
    __tablename__ = "payments"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    invoice_id: Mapped[str] = mapped_column(String(64), unique=True)
    amount: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class CachedData(Base):
    __tablename__ = "cached_data"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    data: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create(self, telegram_id: int, username: str, full_name: str) -> User:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if not user:
            user = User(telegram_id=telegram_id, username=username, full_name=full_name)
            self.session.add(user)
            await self.session.commit()
            await self.session.refresh(user)
        else:
            if user.username != username or user.full_name != full_name:
                user.username = username
                user.full_name = full_name
                await self.session.commit()
        return user

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def update_balance(self, telegram_id: int, amount: float) -> float:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        user = result.scalar_one_or_none()
        if user:
            user.balance = round(user.balance + amount, 4)
            if amount < 0:
                user.total_spent = round(user.total_spent + abs(amount), 4)
            await self.session.commit()
            return user.balance
        return 0.0

    async def get_all_users(self) -> List[User]:
        result = await self.session.execute(select(User))
        return result.scalars().all()


class ActivationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, activation_id: str, service: str, service_name: str,
                     country_id: int, country_name: str, phone_number: str, cost: float) -> Activation:
        activation = Activation(
            user_id=user_id, activation_id=activation_id, service=service,
            service_name=service_name, country_id=country_id, country_name=country_name,
            phone_number=phone_number, cost=cost
        )
        self.session.add(activation)
        await self.session.commit()
        await self.session.refresh(activation)
        return activation

    async def get_by_activation_id(self, activation_id: str) -> Optional[Activation]:
        result = await self.session.execute(select(Activation).where(Activation.activation_id == activation_id))
        return result.scalar_one_or_none()

    async def get_user_activations(self, user_id: int, limit: int = 10) -> List[Activation]:
        result = await self.session.execute(
            select(Activation).where(Activation.user_id == user_id).order_by(Activation.created_at.desc()).limit(limit)
        )
        return result.scalars().all()

    async def get_active_activations(self, user_id: int) -> List[Activation]:
        result = await self.session.execute(
            select(Activation).where(
                Activation.user_id == user_id,
                Activation.status.in_(["waiting", "received"])
            )
        )
        return result.scalars().all()

    async def update_status(self, activation_id: str, status: str, sms_code: str = None):
        result = await self.session.execute(select(Activation).where(Activation.activation_id == activation_id))
        activation = result.scalar_one_or_none()
        if activation:
            activation.status = status
            if sms_code:
                activation.sms_code = sms_code
            if status in ["completed", "cancelled"]:
                activation.completed_at = datetime.utcnow()
            await self.session.commit()
        return activation


class PaymentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, invoice_id: str, amount: float, currency: str) -> Payment:
        payment = Payment(user_id=user_id, invoice_id=invoice_id, amount=amount, currency=currency)
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def get_by_invoice_id(self, invoice_id: str) -> Optional[Payment]:
        result = await self.session.execute(select(Payment).where(Payment.invoice_id == invoice_id))
        return result.scalar_one_or_none()

    async def mark_paid(self, invoice_id: str) -> Optional[Payment]:
        result = await self.session.execute(select(Payment).where(Payment.invoice_id == invoice_id))
        payment = result.scalar_one_or_none()
        if payment and payment.status == "pending":
            payment.status = "paid"
            payment.paid_at = datetime.utcnow()
            await self.session.commit()
            return payment
        return None

    async def get_user_payments(self, user_id: int, limit: int = 10) -> List[Payment]:
        result = await self.session.execute(
            select(Payment).where(Payment.user_id == user_id).order_by(Payment.created_at.desc()).limit(limit)
        )
        return result.scalars().all()


class CacheRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, key: str) -> Optional[str]:
        result = await self.session.execute(
            select(CachedData).where(CachedData.cache_key == key, CachedData.expires_at > datetime.utcnow())
        )
        cached = result.scalar_one_or_none()
        return cached.data if cached else None

    async def set(self, key: str, data: str, ttl_seconds: int = 300):
        from datetime import timedelta
        expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
        result = await self.session.execute(select(CachedData).where(CachedData.cache_key == key))
        cached = result.scalar_one_or_none()
        if cached:
            cached.data = data
            cached.expires_at = expires_at
        else:
            cached = CachedData(cache_key=key, data=data, expires_at=expires_at)
            self.session.add(cached)
        await self.session.commit()

    async def delete_expired(self):
        result = await self.session.execute(select(CachedData).where(CachedData.expires_at <= datetime.utcnow()))
        expired = result.scalars().all()
        for item in expired:
            await self.session.delete(item)
        await self.session.commit()
