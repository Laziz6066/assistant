from datetime import datetime, date
from sqlalchemy import BigInteger, ForeignKey, String, DateTime, Date, Integer, Numeric
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from dotenv import load_dotenv
import os
from sqlalchemy import Text, JSON


load_dotenv()
engine = create_async_engine(url=os.getenv('POSTGRESQL'))

async_session = async_sessionmaker(engine, expire_on_commit=False)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    user_name: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(8))

    user_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(250), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)

    total_spent: Mapped[int]   = mapped_column(Numeric(12, 2), default=0)
    bonus_balance: Mapped[int] = mapped_column(Integer, default=0)
    discount_rate: Mapped[int] = mapped_column(Integer, default=0)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name_uz: Mapped[str] = mapped_column(String(500))
    name_ru: Mapped[str] = mapped_column(String(500))


class Item(Base):
    __tablename__ = 'items'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name_uz: Mapped[str] = mapped_column(String(500))
    name_ru: Mapped[str] = mapped_column(String(500))
    description_uz: Mapped[str] = mapped_column(Text)
    description_ru: Mapped[str] = mapped_column(Text)
    price: Mapped[int] = mapped_column()
    photo: Mapped[list] = mapped_column(JSON)
    in_stock: Mapped[bool] = mapped_column(default=False)
    category: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    orders: Mapped[list["Order"]] = relationship(
        back_populates="item",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class Order(Base):
    __tablename__ = 'orders'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    photo: Mapped[list] = mapped_column(JSON)
    shipping_method: Mapped[str] = mapped_column(String(500))
    user: Mapped[int] = mapped_column(ForeignKey("users.id"))
    item_id:    Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"),
        nullable=True,
    )
    item:       Mapped["Item"] = relationship(
        back_populates="orders",
        lazy="selectin",
    )
    quantity: Mapped[int] = mapped_column(nullable=True)
    total_price: Mapped[int] = mapped_column(nullable=True)
    deposit: Mapped[int] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_paid: Mapped[bool] = mapped_column(default=False)
    is_delivered: Mapped[bool] = mapped_column(default=False)



async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)