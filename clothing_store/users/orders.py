import clothing_store.users.keyboards as kb
from clothing_store import config
from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardRemove
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
import clothing_store.database.requests as rq
from clothing_store.admin.state import AddOrder, Register
from zoneinfo import ZoneInfo
from aiogram import Bot


order_router = Router()
UZ_TZ = ZoneInfo("Asia/Tashkent")


@order_router.message(F.text.in_({'На заказ', 'Buyurtma'}))
async def add_order(message: Message, state: FSMContext):
    user = await rq.get_user_reg(message.from_user.id)           # получить запись
    if user is None or not all([user.full_name, user.phone, user.address]):  # проверить заполненность
        await state.set_state(Register.full_name)            # запустить регистрацию
        await message.answer("Для оформления заказа необходимо зарегистрироваться.\n"
                             "Введите ФИО:")
        return

    # профиль полный -> продолжать оформление заказа
    await state.set_state(AddOrder.photo)
    await message.answer(config.order[user.language])



@order_router.message(Register.full_name)
async def reg_full_name(message: Message, state: FSMContext):
    await rq.update_user(message.from_user.id, full_name=message.text.strip())
    await state.set_state(Register.phone)
    kb_phone = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отправить номер", request_contact=True)]],
        resize_keyboard=True
    )
    await message.answer("Отправьте номер телефона:", reply_markup=kb_phone)

@order_router.message(Register.phone, F.contact)
async def reg_phone(message: Message, state: FSMContext):
    await rq.update_user(message.from_user.id, phone=message.contact.phone_number)
    await state.set_state(Register.address)
    await message.answer("Введите адрес:", reply_markup=ReplyKeyboardRemove())

@order_router.message(Register.address)
async def reg_address(message: Message, state: FSMContext):
    await rq.update_user(message.from_user.id, address=message.text.strip())
    if message.from_user.username:
        await rq.update_user(message.from_user.id, user_link=f"https://t.me/{message.from_user.username}")
    await message.answer("Регистрация завершена, продолжим оформление заказа.")
    # вернуть пользователя в цепочку оформления
    await state.set_state(AddOrder.photo)
    lang_choice = await rq.get_user(message.from_user.id)
    print(lang_choice)
    await message.answer(config.order[lang_choice])


@order_router.message(F.photo, AddOrder.photo)
async def order_photo(message: Message, state: FSMContext):
    keyboard = await kb.order_choice()
    photo_id = message.photo[-1].file_id
    await state.update_data(photo=photo_id)
    await state.set_state(AddOrder.shipping_method)

    await message.answer("Выберите способ доставки:"
                         "\n✈️ Авиа-карго (быстрее, дороже)"
                         "\n🚛 Авто-карго (дольше, дешевле)", reply_markup=keyboard)


@order_router.message(AddOrder.shipping_method)
async def order_shipping(message: Message, state: FSMContext, bot: Bot):
    await state.update_data(shipping_method=message.text.strip())
    data = await state.get_data()
    photo_id = data.get('photo')

    db_user = await rq.get_user_reg(message.from_user.id)

    order = await rq.add_order(
        photo=photo_id,
        shipping_method=data['shipping_method'],
        user=db_user.id
    )
    local_dt = order.created_at.astimezone(UZ_TZ)
    admin_text = (
        f"🆕 Новый заказ # {order.id}\n"
        f"👤 Пользователь: {db_user.full_name}\n"
        f"📱 Телефон: {db_user.phone}\n"
        f"🏘 Адрес: {db_user.address}\n"
        f"🔗 Username: {db_user.user_link if db_user.user_link else 'не указан'}\n"
        f"🚚 Способ доставки: {order.shipping_method}\n"
        f"⏰ Время заказа: {local_dt:%Y-%m-%d %H:%M:%S}"
    )

    await bot.send_photo(chat_id=661394290, photo=photo_id, caption=admin_text)

    await state.clear()
    await message.answer("Заказ успешно принят, скоро наш менеджер свяжется с Вами!")
