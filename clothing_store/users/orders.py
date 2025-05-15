import clothing_store.users.keyboards as kb
from clothing_store import config
from aiogram import Router, F, Bot
from aiogram.types import (Message, ReplyKeyboardRemove,
                           KeyboardButton, ReplyKeyboardMarkup)
from aiogram.fsm.context import FSMContext
import clothing_store.database.requests as rq
from clothing_store.admin.state import AddOrder, RegisterOrder
from zoneinfo import ZoneInfo

# 👇 новая утилита
from clothing_store.utils.user_helpers import get_missing_fields, ORDER_REQUIRED

order_router = Router()
UZ_TZ = ZoneInfo("Asia/Tashkent")


# ──────────────────────────────────────────────────────────────────────
# Вход в сценарий «На заказ»
# ──────────────────────────────────────────────────────────────────────
@order_router.message(F.text.in_({'На заказ', 'Buyurtma'}))
async def add_order(message: Message, state: FSMContext):
    # 1. Получаем (или создаём) пользователя
    user = await rq.get_user_reg(message.from_user.id)
    if user is None:
        # создаём минимальную запись, если юзера нет совсем
        async for session in rq.get_async_session():
            await rq.add_user(
                user_id=message.from_user.id,
                user_name=message.from_user.username or '',
                language='ru',
                session=session,
            )
        user = await rq.get_user_reg(message.from_user.id)

    # 2. Проверяем, какие поля ещё не заполнены
    missing = get_missing_fields(user, ORDER_REQUIRED)

    if missing:
        field = missing[0]              # начинаем с первого «дырыщего» поля
        if field == "full_name":
            await state.set_state(RegisterOrder.full_name)
            await message.answer("Для оформления заказа нужно зарегистрироваться.\nВведите ФИО:")
        elif field == "phone":
            await state.set_state(RegisterOrder.phone)
            kb_phone = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Отправить номер", request_contact=True)]],
                resize_keyboard=True
            )
            await message.answer("Отправьте номер телефона:", reply_markup=kb_phone)
        elif field == "address":
            await state.set_state(RegisterOrder.address)
            await message.answer("Введите адрес:")
        return

    # 3. Всё уже заполнено — идём дальше к фото заказа
    await state.set_state(AddOrder.photo)
    await message.answer(config.order[user.language])


# ──────────────────────────────────────────────────────────────────────
# Шаги регистрации / дозаполнения данных
# ──────────────────────────────────────────────────────────────────────
@order_router.message(RegisterOrder.full_name)
async def reg_full_name(message: Message, state: FSMContext):
    await rq.update_user(message.from_user.id, full_name=message.text.strip())

    user = await rq.get_user_reg(message.from_user.id)
    missing = get_missing_fields(user, ORDER_REQUIRED)

    if "phone" in missing:
        await state.set_state(RegisterOrder.phone)
        kb_phone = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отправить номер", request_contact=True)]],
            resize_keyboard=True
        )
        await message.answer("Отправьте номер телефона:", reply_markup=kb_phone)
    elif "address" in missing:
        await state.set_state(RegisterOrder.address)
        await message.answer("Введите адрес:", reply_markup=ReplyKeyboardRemove())
    else:
        # ничего не осталось — к шагу загрузки фото
        await _finish_registration_and_ask_photo(message, state)


@order_router.message(RegisterOrder.phone, F.contact)
async def reg_phone(message: Message, state: FSMContext):
    await rq.update_user(message.from_user.id, phone=message.contact.phone_number)

    user = await rq.get_user_reg(message.from_user.id)
    missing = get_missing_fields(user, ORDER_REQUIRED)

    if "address" in missing:
        await state.set_state(RegisterOrder.address)
        await message.answer("Введите адрес:", reply_markup=ReplyKeyboardRemove())
    else:
        await _finish_registration_and_ask_photo(message, state)


@order_router.message(RegisterOrder.address)
async def reg_address(message: Message, state: FSMContext):
    await rq.update_user(message.from_user.id, address=message.text.strip())
    if message.from_user.username:
        await rq.update_user(message.from_user.id,
                             user_link=f"https://t.me/{message.from_user.username}")

    await _finish_registration_and_ask_photo(message, state)


async def _finish_registration_and_ask_photo(message: Message, state: FSMContext):
    """Общий шаг: регистрация закончена — просим фото и переходим к оформлению."""
    await message.answer("Регистрация завершена, продолжим оформление заказа.")
    await state.set_state(AddOrder.photo)
    lang_choice = await rq.get_user(message.from_user.id)
    await message.answer(config.order[lang_choice], reply_markup=ReplyKeyboardRemove())


# ──────────────────────────────────────────────────────────────────────
# Дальнейшие шаги оформления заказа (не менялись)
# ──────────────────────────────────────────────────────────────────────
@order_router.message(F.photo, AddOrder.photo)
async def order_photo(message: Message, state: FSMContext):
    keyboard = await kb.order_choice()
    photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)
    await state.set_state(AddOrder.shipping_method)

    await message.answer(
        "Выберите способ доставки:"
        "\n✈️ Авиа-карго (быстрее, дороже)"
        "\n🚛 Авто-карго (дольше, дешевле)",
        reply_markup=keyboard
    )


@order_router.message(AddOrder.shipping_method)
async def order_shipping(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(shipping_method=message.text.strip())
    data = await state.get_data()
    photo_id = data.get('photo')

    db_user = await rq.get_user_reg(message.from_user.id)
    keyboard = await kb.get_main_keyboard(message.from_user.id)

    order = await rq.add_order(
        photo=photo_id,
        shipping_method=data['shipping_method'],
        user=db_user.id
    )

    local_dt = order.created_at.astimezone(UZ_TZ)
    admin_text = (
        f"⚠️ Новый заказ (по фото) № заказа: {order.id}\n"
        f"👤 Пользователь: {db_user.full_name}\n"
        f"📱 Телефон: {db_user.phone}\n"
        f"🏘 Адрес: {db_user.address}\n"
        f"🔗 Username: {db_user.user_link or 'не указан'}\n"
        f"🚚 Способ доставки: {order.shipping_method}\n"
        f"⏰ Время заказа: {local_dt:%Y-%m-%d %H:%M:%S}"
    )

    await bot.send_photo(chat_id=661394290, photo=photo_id, caption=admin_text)

    await state.clear()
    await message.answer("Заказ успешно принят, скоро наш менеджер свяжется с Вами!",
                         reply_markup=keyboard)
