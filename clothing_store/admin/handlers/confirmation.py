import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from clothing_store.admin.state import SetPaidSG
import clothing_store.database.requests as rq
from clothing_store.config import ADMINS
import clothing_store.admin.a_keyboards as kb_admin
from clothing_store.users import keyboards as kb_user
from clothing_store.users.bonus import BonusService

status_router = Router()


@status_router.message(F.text.casefold() == "подтвердить")
async def ask_order_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return

    await message.answer("Введите ID заказа для подтверждения")
    await state.set_state(SetPaidSG.waiting_order_id)


@status_router.message(SetPaidSG.waiting_order_id)
async def check_order_data(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await state.clear()
        return

    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer("❗️ Нужен числовой ID заказа. Попробуйте ещё раз или /cancel.")
        return

    order_id = int(text)
    order = await rq.get_order(order_id)

    if not order:
        await message.answer(f"Заказ №{order_id} не найден.")
        await state.clear()
        return

    if order.is_paid:
        await message.answer(f"Заказ №{order_id} уже подтверждён.")
        await state.clear()
        return

    # Сохраняем данные заказа в состоянии
    await state.update_data(
        order_id=order_id,
        current_quantity=order.quantity,
        current_total_price=order.total_price,
        current_deposit=order.deposit,
        current_status=order.status
    )

    # Проверяем, какие поля уже заполнены
    missing_fields = []
    if order.quantity is None:
        missing_fields.append("quantity")
    if order.total_price is None:
        missing_fields.append("total_price")
    if order.deposit is None:
        missing_fields.append("deposit")
    if order.status is None:
        missing_fields.append("status")

    if missing_fields:
        # Если есть незаполненные поля, начинаем их запрашивать
        next_field = missing_fields[0]
        if next_field == "quantity":
            await message.answer("Введите количество товара")
            await state.set_state(SetPaidSG.quantity)
        elif next_field == "total_price":
            await message.answer("Введите сумму товара")
            await state.set_state(SetPaidSG.total_price)
        elif next_field == "deposit":
            await message.answer("Введите сумму предоплаты")
            await state.set_state(SetPaidSG.deposit)
        elif next_field == "status":
            keyboard = await kb_admin.status_keyboard(message.from_user.id)
            await message.answer("Введите статус товара", reply_markup=keyboard)
            await state.set_state(SetPaidSG.status)
    else:
        # Все поля заполнены - переходим к подтверждению
        await show_confirmation(message, state)


async def show_confirmation(message: Message, state: FSMContext):
    state_data = await state.get_data()
    order_id = state_data['order_id']

    # Используем новые данные, если они есть, иначе существующие
    quantity = state_data.get('quantity', state_data.get('current_quantity'))
    total_price = state_data.get('total_price', state_data.get('current_total_price'))
    deposit = state_data.get('deposit', state_data.get('current_deposit'))
    status = state_data.get('status', state_data.get('current_status'))

    remains = int(total_price) - int(deposit) if total_price and deposit else 0

    summary_message = (
        f"Проверьте данные перед подтверждением:\n"
        f"Номер заказа: {order_id}\n"
        f"Количество: {quantity or 'не указано'}\n"
        f"Сумма товара: {total_price or 'не указано'}\n"
        f"Предоплата: {deposit or 0}\n"
        f"Остаток: {remains if total_price and deposit else 0}\n"
        f"Статус: {status or 'не указан'}\n\n"
        f"Подтвердить изменения? (Да/Нет)"
    )

    await message.answer(summary_message, reply_markup=await kb_admin.confirmation_keyboard())
    await state.set_state(SetPaidSG.confirmation)


@status_router.message(SetPaidSG.quantity)
async def add_quantity(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректное число")
        return

    await state.update_data(quantity=int(message.text))
    state_data = await state.get_data()

    # Проверяем, нужно ли запрашивать следующие поля
    if state_data.get('current_total_price') is None:
        await message.answer("Введите сумму товара")
        await state.set_state(SetPaidSG.total_price)
    else:
        await show_confirmation(message, state)


@status_router.message(SetPaidSG.total_price)
async def add_total_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректную сумму")
        return

    await state.update_data(total_price=int(message.text))
    state_data = await state.get_data()

    if state_data.get('current_deposit') is None:
        await message.answer("Введите сумму предоплаты")
        await state.set_state(SetPaidSG.deposit)
    else:
        await show_confirmation(message, state)


@status_router.message(SetPaidSG.deposit)
async def add_deposit(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректную сумму")
        return

    await state.update_data(deposit=int(message.text))
    state_data = await state.get_data()

    if state_data.get('current_status') is None:
        keyboard = await kb_admin.status_keyboard(message.from_user.id)
        await message.answer("Введите статус товара", reply_markup=keyboard)
        await state.set_state(SetPaidSG.status)
    else:
        await show_confirmation(message, state)


@status_router.message(SetPaidSG.status)
async def add_status(message: Message, state: FSMContext):
    await state.update_data(status=message.text)
    await show_confirmation(message, state)


@status_router.message(SetPaidSG.confirmation, F.text.casefold().in_(["да", "нет"]))
async def confirm_changes(message: Message, state: FSMContext):
    if message.text.casefold() == "нет":
        await message.answer("Изменения отменены.",
                             reply_markup=await kb_user.get_main_keyboard(message.from_user.id))
        await state.clear()
        return

    state_data = await state.get_data()
    order_id = state_data['order_id']

    # Используем новые данные, если они есть, иначе существующие
    quantity = state_data.get('quantity', state_data.get('current_quantity'))
    total_price = state_data.get('total_price', state_data.get('current_total_price'))
    deposit = state_data.get('deposit', state_data.get('current_deposit'))
    status = state_data.get('status', state_data.get('current_status'))

    order = await rq.set_order_paid(
        order_id=order_id,
        quantity=quantity,
        total_price=total_price,
        deposit=deposit,
        status=status
    )

    if order and order.is_delivered:
        await BonusService.check_and_apply_bonuses(order_id)

    if not order:
        await message.answer(f"Заказ №{order_id} не найден или уже оплачен.")
        await state.clear()
        return

    # Отправляем администратору подтверждение
    remains = int(total_price) - int(deposit) if total_price and deposit else 0
    await message.answer(
        f"✅ Заказ №{order_id} успешно обновлен:\n"
        f"Количество: {quantity or 'не изменилось'}\n"
        f"Сумма заказа: {total_price or 'не изменилась'}\n"
        f"Предоплата: {deposit or 'не изменилась'}\n"
        f"Остаток: {remains}\n"
        f"Статус: {status or 'не изменился'}",
        reply_markup=await kb_user.get_main_keyboard(message.from_user.id)
    )

    # Отправляем уведомление пользователю
    try:
        user_id = order.user_id if hasattr(order, 'user_id') else order.user
        user_obj = await rq.get_user_by_pk(user_id)
        if user_obj:
            user_message = (
                f"Ваш заказ подтверждён и передан в обработку!\n"
                f"Номер заказа: №{order_id}\n"
                f"Сумма заказа: {total_price or 'не указана'}\n"
                f"Количество: {quantity or 'не указано'}\n"
                f"Предоплата: {deposit or 0}\n"
                f"Статус: {status or 'не указан'}\n"
                f"Остаток суммы товара: {remains if total_price and deposit else 0}"
            )
            await message.bot.send_message(user_obj.tg_id, user_message)
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления пользователю: {e}")

    await state.clear()