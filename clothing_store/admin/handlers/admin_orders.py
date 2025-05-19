import logging
from aiogram import F, Router, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from clothing_store.admin.state import UpdateOrderStatus
import clothing_store.database.requests as rq
from clothing_store.database.models import Order, User
from clothing_store.users.bonus import BonusService
from clothing_store.config import ADMINS
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from clothing_store.database.models import async_session


admin_order_router = Router()


@admin_order_router.message(F.text == "Управление заказами")
async def manage_orders(message: Message):
    if message.from_user.id not in ADMINS:
        return

    # Показываем список заказов для управления
    keyboard = await get_orders_list_keyboard()
    await message.answer("Выберите заказ для изменения статуса:", reply_markup=keyboard)


async def get_orders_list_keyboard():
    orders = await rq.get_recent_orders()  # Нужно реализовать эту функцию
    builder = InlineKeyboardBuilder()

    for order in orders:
        builder.add(InlineKeyboardButton(
            text=f"Заказ #{order.id} - {order.status}",
            callback_data=f"admin_order_{order.id}"
        ))

    builder.adjust(1)
    return builder.as_markup()


@admin_order_router.callback_query(F.data.startswith("admin_order_"))
async def select_order(callback: CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split("_")[-1])
    order = await rq.get_order(order_id)

    if not order:
        await callback.answer("Заказ не найден")
        return

    await state.update_data(order_id=order_id)
    await state.set_state(UpdateOrderStatus.select_status)

    keyboard = await get_status_keyboard(order)
    await callback.message.edit_text(
        f"Заказ #{order.id}\nТекущий статус: {order.status}\nВыберите новый статус:",
        reply_markup=keyboard
    )


async def get_status_keyboard(order: Order):
    builder = InlineKeyboardBuilder()

    # Статусы для товаров в наличии
    if not order.item_id:  # Предполагаем, что заказ по фото - это товар на заказ
        statuses = [
            ("Заказ оформлен", "status_ordered"),
            ("На складе у продавца", "status_seller_warehouse"),
            ("На складе в Китае", "status_china_warehouse"),
            ("В пути в Ташкент", "status_transit"),
            ("На таможенном складе", "status_customs"),
            ("Сортировка", "status_sorting"),
            ("Передан курьеру", "status_courier"),
            ("Доставлен (завершить)", "status_delivered")
        ]
    else:
        # Статусы для товаров в наличии
        statuses = [
            ("Заказ оформлен", "status_ordered"),
            ("Передан курьеру", "status_courier"),
            ("Доставлен (завершить)", "status_delivered")
        ]

    for text, data in statuses:
        builder.add(InlineKeyboardButton(text=text, callback_data=f"{data}_{order.id}"))

    builder.adjust(1)
    return builder.as_markup()


@admin_order_router.callback_query(F.data.startswith("status_"))
async def update_order_status(callback: CallbackQuery, bot: Bot):
    status_type = callback.data.split("_")[1]
    order_id = int(callback.data.split("_")[-1])

    status_map = {
        "ordered": "Заказ оформлен",
        "seller": "На складе у продавца",
        "china": "На складе в Китае",
        "transit": "В пути в Ташкент",
        "customs": "На таможенном складе",
        "sorting": "Сортировка",
        "courier": "Передан курьеру",
        "delivered": "Доставлен"
    }

    new_status = status_map.get(status_type, "Неизвестный статус")
    is_delivered = status_type == "delivered"

    async with async_session() as session:
        order = await session.get(Order, order_id)
        if not order:
            await callback.answer("Заказ не найден")
            return

        order.status = new_status
        if is_delivered:
            order.is_delivered = True  # Помечаем заказ как доставленный
            # **Не устанавливаем order.is_bonus_calculated вручную здесь** (убран прежний order.is_bonus_calculated = True)
            # Получаем пользователя, связанного с заказом, и обновляем его общую сумму потраченного
            user = await session.get(User, order.user_id)
            if user:
                user.total_spent = (user.total_spent or 0) + (order.total_price or 0)  # увеличиваем total_spent пользователя на сумму заказа

        await session.commit()

    if is_delivered:
        await BonusService.check_and_apply_bonuses(
            order.id)  # Начисляем бонусы после коммита, когда заказ помечен доставленным
    try:
        user_id = order.user_id if hasattr(order, 'user_id') else order.user
        user = await rq.get_user_by_pk(user_id)
        if user:
            await bot.send_message(
                user.tg_id,
                f"Статус вашего заказа №{order_id} изменен: {new_status}"
            )
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления: {e}")

    # Если заказ завершен, обновляем список заказов
    if is_delivered:
        keyboard = await get_orders_list_keyboard()  # Получаем обновленный список
        try:
            await callback.message.edit_text(
                "Заказ завершен и удален из списка управления",
                reply_markup=keyboard
            )
        except:
            await callback.message.answer(
                "Заказ завершен и удален из списка управления",
                reply_markup=keyboard
            )
    else:
        await callback.answer(f"Статус обновлен: {new_status}")
        await callback.message.edit_text(
            f"Статус заказа #{order_id} успешно обновлен на: {new_status}"
        )