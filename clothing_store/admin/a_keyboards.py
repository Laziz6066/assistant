from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from clothing_store.config import ADMINS
from clothing_store.database.requests import get_categories


async def admin_keyboard(user_id: int) -> ReplyKeyboardMarkup | None:
    if user_id in ADMINS:
        buttons = [
            [KeyboardButton(text='Добавить категорию'), KeyboardButton(text='Удалить категорию')],
            [KeyboardButton(text='Добавить товар'), KeyboardButton(text='Удалить товар')],
            [KeyboardButton(text='Изменить статус'), KeyboardButton(text='На главную')]
        ]
        return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    else:
        return None


async def add_categories(for_admin=False):
    all_categories = await get_categories()
    keyboard = InlineKeyboardBuilder()

    for category in all_categories:
        cb_data = f'add_category_{category.id}' if for_admin else f'show_category_{category.id}'
        keyboard.add(InlineKeyboardButton(text=category.name_ru, callback_data=cb_data))

    keyboard.add(InlineKeyboardButton(text='На главную', callback_data='to_main'))

    return keyboard.adjust(2).as_markup()


async def add_categories_item():
    all_categories = await get_categories()
    keyboard = InlineKeyboardBuilder()

    for category in all_categories:
        cb_data = f'add_item_category_{category.id}'
        keyboard.add(InlineKeyboardButton(text=category.name_ru, callback_data=cb_data))

    keyboard.add(InlineKeyboardButton(text='На главную', callback_data='to_main'))

    return keyboard.adjust(2).as_markup()