from datetime import datetime

from clothing_store.database.models import async_session
from clothing_store.database.models import User, Category, Item
from sqlalchemy import select, update, delete
import logging
from sqlalchemy.ext.asyncio import AsyncSession


async def get_async_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def get_user(user_id: int):
    async with async_session() as session:
        result = await session.scalars(select(User.language).where(User.tg_id == user_id))
        return result.first()  # Get the first value


async def get_categories():
    async with async_session() as session:
        return await session.scalars(select(Category))


async def get_items(category_id):
    async with async_session() as session:
        query = select(Item).where(
            Item.category == category_id)

        return await session.scalars(query)


async def add_user(user_id: int, user_name: str, language: str, session: AsyncSession):
    user = User(tg_id=user_id, user_name=user_name, language=language)
    session.add(user)
    await session.commit()


async def user_exists(user_id: int, session: AsyncSession) -> bool:
    result = await session.execute(select(User).filter_by(tg_id=user_id))
    return result.scalars().first() is not None


async def add_category(name_uz: str, name_ru: str, ):
    async with async_session() as session:
        category = Category(name_uz=name_uz, name_ru=name_ru)
        session.add(category)
        await session.commit()


async def add_item(
        name_uz: str,
        name_ru: str,
        description_uz: str,
        description_ru: str,
        price: int,
        photo: list,
        category: int
):
    logging.info(f"Добавление товара: {name_uz}, {name_ru}, {description_uz}, {description_ru}, "
                 f"{price}, {photo}, {category}")

    async with async_session() as session:
        item = Item(
            name_uz=name_uz,
            name_ru=name_ru,
            description_uz=description_uz,
            description_ru=description_ru,
            price=price,
            photo=photo,
            category=category
        )
        session.add(item)
        await session.commit()


async def delete_item(item_id: int):
    async with async_session() as session:
        await session.execute(delete(Item).where(Item.id == item_id))
        await session.commit()


async def update_item(item_id: int, name_ru: str, name_uz: str, description_ru: str,
                      description_uz: str, price: int):
    async with async_session() as session:
        await session.execute(
            update(Item)
            .where(Item.id == item_id)
            .values(
                name_ru=name_ru,
                name_uz=name_uz,
                description_ru=description_ru,
                description_uz=description_uz,
                price=price
            )
        )
        await session.commit()


async def get_item_for_update(item_id: int):
    async with async_session() as session:
        result = await session.execute(select(Item).where(Item.id == item_id))
        return result.scalars().first()


async def delete_category_by_name(category_name: str):
    async with async_session() as session:
        await session.execute(delete(Category).where(Category.name_ru == category_name))
        await session.commit()


# В requests.py добавьте:
async def update_user_language(user_id: int, new_language: str, session: AsyncSession):
    await session.execute(
        update(User).where(User.tg_id == user_id).values(language=new_language)
    )
    await session.commit()


async def get_item(item_id: int) -> Item | None:
    async with async_session() as session:
        result = await session.execute(select(Item).where(Item.id == item_id))
        return result.scalar_one_or_none()