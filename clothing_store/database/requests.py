from datetime import datetime, UTC
from sqlalchemy.orm import selectinload
from clothing_store.database.models import async_session
from clothing_store.database.models import User, Category, Item, Order
from sqlalchemy import select, update, delete
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from typing import AsyncGenerator


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def get_user(user_id: int):
    async with async_session() as session:
        result = await session.scalars(select(User.language).where(User.tg_id == user_id))
        return result.first()


async def get_user_reg(user_id: int):
    """
    Вернуть объект User по tg_id или None, если такого пользователя нет.
    """
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.tg_id == user_id)
        )
        return result.scalars().first()


async def get_user_by_pk(pk_id: int) -> User | None:
    """
    Вернуть объект User по его первичному id (колонка users.id).
    Если запись не найдена – вернуть None.
    """
    async with async_session() as session:
        return await session.get(User, pk_id)


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


async def update_user_language(user_id: int, new_language: str, session: AsyncSession):
    await session.execute(
        update(User).where(User.tg_id == user_id).values(language=new_language)
    )
    await session.commit()


async def get_item(item_id: int) -> Item | None:
    async with async_session() as session:
        result = await session.execute(select(Item).where(Item.id == item_id))
        return result.scalar_one_or_none()


async def update_user(user_id: int, **fields):

    if not fields:
        return

    async with async_session() as session:
        await session.execute(
            update(User)
            .where(User.tg_id == user_id)
            .values(**fields)
        )
        await session.commit()


async def add_order(photo: list | None = None, shipping_method: str | None = None,
                    user: int | None = None, item_id: int | None = None,
                    quantity: int | None = None, total_price: int | None = None,
                    status: str | None = None):
    async with async_session() as session:
        order = Order(photo=photo or [], shipping_method=shipping_method, user=user,
                      item_id=item_id, quantity=quantity, total_price=total_price,
                      status=status, created_at=datetime.now(UTC))
        session.add(order)
        await session.commit()
        return order


async def get_unpaid_orders():
    """
    Вернуть список всех заказов, где is_paid = False.
    Используется, если вы захотите выводить список кнопок вместо ручного ввода.
    """
    async with async_session() as session:
        result = await session.scalars(
            select(Order)
            .where(Order.is_paid.is_(False))
            .options(selectinload(Order.item))      # подтягиваем товар сразу
        )
        return result.all()


# ----------------------------------------------------------------------
async def set_order_paid(
    order_id: int,
    quantity: int | None = None,
    total_price: int | None = None,
    deposit: int | None = None,
    status: str | None = None
) -> Order | None:
    """
    Пометить заказ как оплаченный, обновить дополнительные поля и вернуть объект Order
    (или None, если не найден / уже оплачен).
    """
    async with async_session() as session:
        order: Order | None = await session.get(Order, order_id)
        if not order or order.is_paid:
            return None

        order.is_paid = True
        if quantity is not None:
            order.quantity = quantity
        if total_price is not None:
            order.total_price = total_price
        if deposit is not None:
            order.deposit = deposit
        if status is not None:
            order.status = status

        await session.commit()
        await session.refresh(order)
        return order


async def get_order(order_id: int) -> Order | None:
    """Вернуть Order по первичному ключу или None."""
    async with async_session() as session:
        return await session.get(Order, order_id)
