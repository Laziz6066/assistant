import logging

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from clothing_store.admin.state import SetPaidSG
import clothing_store.database.requests as rq
from clothing_store.config import ADMINS
import clothing_store.admin.a_keyboards as kb_admin
from clothing_store.users import keyboards as kb_user



status_router = Router()


@status_router.message(F.text.casefold() == "подтвердить")
async def ask_order_id(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return

    await message.answer("Введите количество заказа")
    await state.set_state(SetPaidSG.quantity)


@status_router.message(SetPaidSG.quantity)
async def add_quantity(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректное число")
        return

    await state.update_data(quantity=int(message.text))
    await state.set_state(SetPaidSG.total_price)
    await message.answer("Введите сумму товара")


@status_router.message(SetPaidSG.total_price)
async def add_deposit(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректную сумму")
        return

    await state.update_data(total_price=int(message.text))
    await state.set_state(SetPaidSG.deposit)
    await message.answer("Введите сумму которую заплатил клиент")


@status_router.message(SetPaidSG.deposit)
async def add_deposit(message: Message, state: FSMContext):
    keyboard = await kb_admin.status_keyboard(message.from_user.id)
    if not message.text.isdigit():
        await message.answer("❌ Введите корректную сумму")
        return

    await state.update_data(deposit=int(message.text))
    await state.set_state(SetPaidSG.status)
    await message.answer("Введите статус товара", reply_markup=keyboard)


@status_router.message(SetPaidSG.status)
async def add_status(message: Message, state: FSMContext):

    await state.update_data(status=message.text)
    await state.set_state(SetPaidSG.waiting_order_id)
    await message.answer("Введите Id заказа")


@status_router.message(SetPaidSG.waiting_order_id)
async def set_paid(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        await state.clear()
        return

    text = message.text.strip() if message.text else ""
    if not text.isdigit():
        await message.answer("❗️ Нужен числовой ID заказа. Попробуйте ещё раз или /cancel.")
        return

    order_id = int(text)
    state_data = await state.get_data()

    remains = int(state_data.get('total_price')) - int(state_data.get('deposit'))
    summary_message = (
        f"Проверьте данные перед подтверждением:\n"
        f"Номер заказа: {order_id}\n"
        f"Количество: {state_data.get('quantity', 'не указано')}\n"
        f"Сумма товара: {state_data.get('total_price', 'не указано')}\n"
        f"Предоплата: {state_data.get('deposit', 'не указано')}\n"
        f"Остаток: {remains}\n"
        f"Статус: {state_data.get('status', 'не указан')}\n\n"
        f"Подтвердить изменения? (Да/Нет)"
    )

    await message.answer(summary_message, reply_markup=await kb_admin.confirmation_keyboard())
    await state.update_data(order_id=order_id)
    await state.set_state(SetPaidSG.confirmation)


@status_router.message(SetPaidSG.confirmation, F.text.casefold().in_(["да", "нет"]))
async def confirm_changes(message: Message, state: FSMContext):
    if message.text.casefold() == "нет":
        await message.answer("Изменения отменены.",
                             reply_markup=await kb_user.get_main_keyboard(message.from_user.id))
        await state.clear()
        return

    state_data = await state.get_data()
    order_id = state_data['order_id']

    order = await rq.set_order_paid(
        order_id=order_id,
        quantity=state_data.get('quantity'),
        total_price=state_data.get('total_price'),
        deposit=state_data.get('deposit'),
        status=state_data.get('status')
    )

    if not order:
        await message.answer(f"Заказ №{order_id} не найден или уже оплачен.")
        await state.clear()
        return

    # Отправляем администратору подтверждение
    remains = int(state_data.get('total_price')) - int(state_data.get('deposit'))
    await message.answer(
        f"✅ Заказ №{order_id} успешно обновлен:\n"
        f"Количество: {state_data.get('quantity', 'не изменилось')}\n"
        f"Сумма заказа: {state_data.get('total_price', 'не изменилось')}\n"
        f"Предоплата: {state_data.get('deposit', 'не изменилась')}\n"
        f"Остаток: {remains}\n"
        f"Статус: {state_data.get('status', 'не изменился')}",
        reply_markup=await kb_user.get_main_keyboard(message.from_user.id)
    )

    # Отправляем уведомление пользователю
    try:
        user_obj = await rq.get_user_by_pk(order.user)
        if user_obj:
            user_message = (
                f"Ваш заказ подтверждён и передан в обработку!\n"
                f"Номер заказа: №{order_id}\n"
                f"Сумма заказа: {order.total_price}\n"
                f"Количество: {state_data.get('quantity', 'не изменилось')}\n"
                f"Предоплата: {state_data.get('deposit', 'не изменилась')}\n"
                f"Статус: {state_data.get('status', 'не изменился')}\n"
                f"Остаток суммы товара: {remains}"
            )
            await message.bot.send_message(user_obj.tg_id, user_message)
    except Exception as e:
        logging.error(f"Ошибка при отправке уведомления пользователю: {e}")

    await state.clear()
