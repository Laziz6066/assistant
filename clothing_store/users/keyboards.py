from aiogram.types import KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv
from clothing_store.database.requests import get_categories, get_items
from aiogram.utils.keyboard import InlineKeyboardBuilder
from clothing_store.config import ADMINS
import clothing_store.database.requests as rq
from clothing_store.config import text_main_menu_key, text_get_contacts


load_dotenv()


async def get_language() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text='🇷🇺 Русский'), KeyboardButton(text="🇺🇿 O'zbekcha")]]

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


async def get_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    lang_choice = await rq.get_user(user_id)
    print('lang_choice key: ', lang_choice)

    buttons = [
        [KeyboardButton(text=text_main_menu_key[lang_choice]['stock']),
         KeyboardButton(text=text_main_menu_key[lang_choice]['order'])],

        [KeyboardButton(text=text_main_menu_key[lang_choice]['bonuses']),
         KeyboardButton(text=text_main_menu_key[lang_choice]['account'])],

        [KeyboardButton(text=text_main_menu_key[lang_choice]['support']),
         KeyboardButton(text=text_main_menu_key[lang_choice]['change_lang'])]]


    if user_id in ADMINS:
        buttons.insert(1, [KeyboardButton(text='Админ панель')])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


async def get_contacts(user_id: int) -> ReplyKeyboardMarkup:
    lang_choice = await rq.get_user(user_id)
    buttons = [
        [KeyboardButton(text=text_get_contacts[lang_choice]["service"]),
         KeyboardButton(text=text_get_contacts[lang_choice]["manager"])],
        [KeyboardButton(text=text_get_contacts[lang_choice]["menu"])]]

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


async def show_categories(user_id, for_admin=False):
    all_categories = await get_categories()
    keyboard = InlineKeyboardBuilder()
    lang_choice = await rq.get_user(user_id)
    text = "На главную" if lang_choice == 'ru' else "Asosiy menyu"

    for category in all_categories:
        cat = category.name_ru if lang_choice == 'ru' else category.name_uz
        cb_data = f'admin_category_{category.id}' if for_admin else f'show_category_{category.id}'
        keyboard.add(InlineKeyboardButton(text=cat, callback_data=cb_data))

    keyboard.add(InlineKeyboardButton(text=text, callback_data='to_main_inline'))

    return keyboard.adjust(2).as_markup()


async def show_items(category_id, user_id, for_admin=False):
    all_items = await get_items(category_id)
    keyboard = InlineKeyboardBuilder()
    lang_choice = await rq.get_user(user_id)
    text = "На главную" if lang_choice == 'ru' else "Asosiy menyu"
    for item in all_items:
        item_name = item.name_ru if lang_choice == 'ru' else item.name_uz
        cb_data = f'admin_item_{item.id}_{category_id}' if for_admin else \
            f'show_item_{item.id}_{category_id}'
        keyboard.add(InlineKeyboardButton(text=item_name, callback_data=cb_data))

    keyboard.add(InlineKeyboardButton(text=text, callback_data='to_main_inline'))

    return keyboard.adjust(1).as_markup()


async def item_keyboard(item_id, user_id):
    lang_choice = await rq.get_user(user_id)
    keyboard = InlineKeyboardBuilder()
    text_1 = "💳 Оплата картой" if lang_choice == 'ru' else "💳 Karta bilan to'lash"
    text_2 = "📆 Оплата наличными" if lang_choice == 'ru' else "📆 Naqd bilan to'lash"
    keyboard.add(InlineKeyboardButton(text=text_1, callback_data=f'pay_card_{item_id}'))
    keyboard.add(InlineKeyboardButton(text=text_2, callback_data=f'installment_{item_id}'))

    if user_id in ADMINS:
        keyboard.add(InlineKeyboardButton(text="Удалить товар", callback_data=f"delete_item_{item_id}"))
        keyboard.add(InlineKeyboardButton(text="Изменить товар", callback_data=f"update_item_{item_id}"))

    return keyboard.adjust(1).as_markup()


async def order_choice() -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text='✈️ Авиа-карго'), KeyboardButton(text="🚛 Авто-карго")]]

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)