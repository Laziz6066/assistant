from aiogram import Router, F
from aiogram.types import Message
import clothing_store.admin.a_keyboards as kb
from clothing_store.config import ADMINS
from clothing_store.users.keyboards import get_main_keyboard


admin_router = Router()


@admin_router.message(F.text == 'Админ панель')
async def admin_panel(message: Message):
    if message.from_user.id in ADMINS:
        keyboard = await kb.admin_keyboard(message.from_user.id)
        await message.answer("Добро пожаловать в Админ панель.", reply_markup=keyboard)
    else:
        await message.answer('У вас нет доступа !!!')


@admin_router.message(F.text == 'На главную')
async def main_menu(message: Message):
    keyboard = await get_main_keyboard(message.from_user.id)
    await message.answer("Вы перешли на главное меню.", reply_markup=keyboard)