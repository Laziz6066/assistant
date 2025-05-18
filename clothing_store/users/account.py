from datetime import datetime
from aiogram import Router, F
from aiogram.types import (Message, ReplyKeyboardRemove,
                           KeyboardButton, ReplyKeyboardMarkup)
from aiogram.fsm.context import FSMContext
import clothing_store.database.requests as rq
from clothing_store.admin.state import PersonalAccount

# 👇 новая утилита
from clothing_store.utils.user_helpers import get_missing_fields, ACCOUNT_REQUIRED

account_router = Router()


def format_user_info(user) -> str:
    """Строка, красиво выводящая данные в «ЛК»."""
    return (
        f"👤 Имя: {user.full_name}\n"
        f"📱 Номер телефона: {user.phone}\n"
        f"💰 Накоплено бонусов: {user.bonus_balance}\n"
        f"💵 Сумма покупок: {user.total_spent} UZS\n"
        f"🔖 Текущая скидка: {user.discount_rate * 100}%\n"
        f"🎂 Дата рождения: {user.date_of_birth.strftime('%d.%m.%Y')}"
    )


# ──────────────────────────────────────────────────────────────────────
# Вход в «Личный кабинет»
# ──────────────────────────────────────────────────────────────────────
@account_router.message(F.text.in_({'Личный кабинет', 'Shaxsiy kabinet'}))
async def personal_account(message: Message, state: FSMContext):
    user = await rq.get_user_reg(message.from_user.id)

    if user is None:
        async for session in rq.get_async_session():
            await rq.add_user(
                user_id=message.from_user.id,
                user_name=message.from_user.username or '',
                language='ru',
                session=session,
            )
        user = await rq.get_user_reg(message.from_user.id)

    missing = get_missing_fields(user, ACCOUNT_REQUIRED)

    if missing:
        field = missing[0]
        if field == "full_name":
            await state.set_state(PersonalAccount.full_name)
            await message.answer(
                "Чтобы перейти в личный кабинет необходимо зарегистрироваться.\nВведите ваше имя:"
            )
        elif field == "phone":
            await state.set_state(PersonalAccount.phone)
            kb_phone = ReplyKeyboardMarkup(
                keyboard=[[KeyboardButton(text="Отправить номер", request_contact=True)]],
                resize_keyboard=True
            )
            await message.answer("Отправьте номер телефона:", reply_markup=kb_phone)
        elif field == "date_of_birth":
            await state.set_state(PersonalAccount.date_of_birth)
            await message.answer(
                "Введите дату рождения (ДД.ММ.ГГГГ), чтобы получать бонусы в день рождения:",
                reply_markup=ReplyKeyboardRemove()
            )
        return

    # Все данные собраны — показываем ЛК
    await _show_account(message, user)


# ──────────────────────────────────────────────────────────────────────
# Шаги дозаполнения данных
# ──────────────────────────────────────────────────────────────────────
@account_router.message(PersonalAccount.full_name)
async def account_full_name(message: Message, state: FSMContext):
    await rq.update_user(message.from_user.id, full_name=message.text.strip())

    user = await rq.get_user_reg(message.from_user.id)
    missing = get_missing_fields(user, ACCOUNT_REQUIRED)

    if "phone" in missing:
        await state.set_state(PersonalAccount.phone)
        kb_phone = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отправить номер", request_contact=True)]],
            resize_keyboard=True
        )
        await message.answer("Отправьте номер телефона:", reply_markup=kb_phone)
    elif "date_of_birth" in missing:
        await state.set_state(PersonalAccount.date_of_birth)
        await message.answer("Введите дату рождения (ДД.ММ.ГГГГ):", reply_markup=ReplyKeyboardRemove())
    else:
        await state.clear()
        await _show_account(message, user)


@account_router.message(PersonalAccount.phone, F.contact)
async def account_phone(message: Message, state: FSMContext):
    await rq.update_user(message.from_user.id, phone=message.contact.phone_number)

    user = await rq.get_user_reg(message.from_user.id)
    missing = get_missing_fields(user, ACCOUNT_REQUIRED)

    if "date_of_birth" in missing:
        await state.set_state(PersonalAccount.date_of_birth)
        await message.answer("Введите дату рождения (ДД.ММ.ГГГГ):", reply_markup=ReplyKeyboardRemove())
    else:
        await state.clear()
        await _show_account(message, user)


@account_router.message(PersonalAccount.date_of_birth)
async def account_date_of_birth(message: Message, state: FSMContext):
    text = message.text.strip()
    try:
        birth_date = datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        await message.answer("❗️ Неверный формат. Введите дату в формате ДД.ММ.ГГГГ.")
        return

    # сохраняем дату
    await rq.update_user(message.from_user.id, date_of_birth=birth_date)
    if message.from_user.username:
        await rq.update_user(message.from_user.id,
                             user_link=f"https://t.me/{message.from_user.username}")

    user = await rq.get_user_reg(message.from_user.id)
    await state.clear()
    await _show_account(message, user)


# ──────────────────────────────────────────────────────────────────────
# Вспомогательная функция
# ──────────────────────────────────────────────────────────────────────
async def _show_account(message: Message, user):
    """Отрисовать данные ЛК."""
    try:
        user_info = format_user_info(user)
        await message.answer(f"📁 Личный кабинет:\n\n{user_info}")
    except AttributeError:
        await message.answer("⚠️ Не все данные заполнены. Проверьте профиль.")
