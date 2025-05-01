from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncAttrs, async_sessionmaker, create_async_engine
from dotenv import load_dotenv
import os
from sqlalchemy import Text, JSON


load_dotenv()
engine = create_async_engine(url=os.getenv('POSTGRESQL'))

async_session = async_sessionmaker(engine)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tg_id = mapped_column(BigInteger, unique=True)
    user_name: Mapped[str] = mapped_column(String(500))
    language: Mapped[str] = mapped_column(String(8))


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


async def async_main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)