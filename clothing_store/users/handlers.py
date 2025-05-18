from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import clothing_store.users.keyboards as kb
import clothing_store.database.requests as rq
from clothing_store import config
from aiogram.types import InputMediaPhoto


router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    keyboard = await kb.get_language()
    lang_choice = await rq.get_user(message.from_user.id)
    if lang_choice:
        keyboard = await kb.get_main_keyboard(message.from_user.id)
        await message.answer(config.text_main_menu[lang_choice], reply_markup=keyboard)
    else:
        await message.answer_photo(
            photo=config.main_photo,
            caption="*Можно написать приветственный текст и отправить фото.\nВыберите язык:",
            reply_markup=keyboard,
        )


@router.message(F.text.in_({'Сменить язык', "Tilni o'zgartirish"}))
async def change_language(message: Message):
    keyboard = await kb.get_language()
    lang_choice = await rq.get_user(message.from_user.id)
    text = "Выберите язык:" if lang_choice == 'ru' else "Tilni tanlang:"
    await message.answer(text, reply_markup=keyboard)


# ─────────────────────────────── Выбор языка ────────────────────────────────
@router.message(F.text.in_({'🇷🇺 Русский', "🇺🇿 O'zbekcha"}))
async def language_selected(message: Message):
    """
    Первый раз — создаём пользователя, дальше просто меняем язык.
    """
    lang_mapping = {'🇷🇺 Русский': 'ru', "🇺🇿 O'zbekcha": 'uz'}
    selected_lang = lang_mapping.get(message.text)

    async with rq.async_session() as session:
        user_exists = await rq.user_exists(message.from_user.id, session)

        if user_exists:
            # запись уже есть — только обновляем язык
            await rq.update_user_language(message.from_user.id, selected_lang, session)
        else:
            # нового пользователя сохраняем в базу
            await rq.add_user(
                message.from_user.id,
                message.from_user.first_name,
                selected_lang,
                session,
            )

    keyboard = await kb.get_main_keyboard(message.from_user.id)
    text = (
        "Выбрано: 🇷🇺 Русский"
        if selected_lang == 'ru'
        else "Tanlandi: 🇺🇿 O'zbekcha"
    )
    await message.answer(text, reply_markup=keyboard)



@router.message(F.text.in_({'Контакты', 'Kontaktlar'}))
async def contacts(message: Message):
    keyboard = await kb.get_contacts(message.from_user.id)
    lang_choice = await rq.get_user(message.from_user.id)
    text = config.text_contacts[lang_choice]
    await message.reply(text=text, reply_markup=keyboard, parse_mode="html")


@router.message(F.text.in_({"Xizmat ko'rsatish markazi", 'Сервисный центр'}))
async def service_contact(message: Message):
    await message.reply("+998901234567")


@router.message(F.text.in_({'Менеджер', 'Menejer'}))
async def manager_contact(message: Message):
    await message.reply("+998999999999")


@router.message(F.text.in_({'Главное меню', 'Asosiy menyu'}))
async def main_menu(message: Message):
    keyboard = await kb.get_main_keyboard(message.from_user.id)
    lang_choice = await rq.get_user(message.from_user.id)
    await message.answer(text=config.text_main_menu[lang_choice], reply_markup=keyboard)


@router.message(F.text.in_({'О нас', 'Biz haqimizda'}))
async def about(message: Message):
    lang_choice = await rq.get_user(message.from_user.id)
    await message.answer("Можно что-то написать или фото отправить (сертификат/гувохнома)")


@router.message(F.text.in_({'Товары в наличии', 'Bor mahsulotlar'}))
async def view_catalog(message: Message):
    lang_choice = await rq.get_user(message.from_user.id)
    await message.answer(config.choice_category[lang_choice],
                         reply_markup=await kb.show_categories(message.from_user.id))


@router.callback_query(F.data.startswith('show_category_'))
async def show_items(callback: CallbackQuery):
    data_parts = callback.data.split('_')
    category_id = int(data_parts[-1])

    items = await rq.get_items(category_id)
    lang_choice = await rq.get_user(callback.from_user.id)

    if not items:
        text = "Товары не найдены." if lang_choice == 'ru' else "Maxsulotlar topilmadi."
        await callback.message.answer(text)
        await callback.answer()
        return

    price_text = "Цена:" if lang_choice == 'ru' else "Narxi:"

    for item in items:
        keyboard = await kb.item_keyboard(item.id, callback.from_user.id)
        item_name = item.name_ru if lang_choice == 'ru' else item.name_uz
        item_description = item.description_ru if lang_choice == 'ru' else item.description_uz
        item_in_stock_ru = "В наличии" if item.in_stock == True else "Под заказ"
        item_in_stock_uz = "Sotuvda mavjud" if item.in_stock == True else "Buyurtma bilan"
        item_in_stock = item_in_stock_ru if lang_choice == 'ru' else item_in_stock_uz
        print(item_in_stock)

        if isinstance(item.photo, list):
            if len(item.photo) > 1:
                media = []
                for index, photo_url in enumerate(item.photo):
                    if index == 0:
                        media.append(
                            InputMediaPhoto(
                                media=photo_url,
                                caption=f"{item_name}\n{item_description}\n{price_text} "
                                        f"<b>{item.price:,.0f} UZS.</b>".replace(",", " "),
                                parse_mode='html'
                            )
                        )
                    else:
                        media.append(InputMediaPhoto(media=photo_url))
                await callback.message.answer_media_group(media=media)
                # Отправляем отдельное сообщение с клавиатурой под товаром
                await callback.message.answer("Выберите действие:", reply_markup=keyboard)
            elif len(item.photo) == 1:
                photo_url = item.photo[0]
                await callback.message.answer_photo(
                    photo=photo_url,
                    caption=f"{item_name}\n{item_description}\n{price_text} "
                            f"<b>{item.price:,.0f} UZS.</b>\n<b>{item_in_stock}</b>".replace(",", " "),
                    reply_markup=keyboard,
                    parse_mode='html'
                )
            else:
                await callback.message.answer(
                    text=f"{item_name}\n{item_description}\n{price_text} "
                         f"<b>{item.price:,.0f} UZS.</b>".replace(",", " "),
                    reply_markup=keyboard,
                    parse_mode='html'
                )
        else:
            await callback.message.answer_photo(
                photo=item.photo,
                caption=f"{item_name}\n{item_description}\n{price_text} "
                        f"<b>{item.price:,.0f} UZS.</b>".replace(",", " "),
                reply_markup=keyboard,
                parse_mode='html'
            )
    await callback.answer()


@router.callback_query(F.data.startswith('to_main_inline'))
async def catalog_main(callback: CallbackQuery):
    lang_choice = await rq.get_user(callback.from_user.id)
    await callback.message.edit_text(config.choice_category[lang_choice],
                                     reply_markup=await kb.show_categories(callback.from_user.id))
    await callback.answer()


@router.message(F.text == "Мои баллы")
async def show_balance(message: Message):
    user = await rq.get_user_reg(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь!")
        return

    level = "Новичок"
    if user.total_spent >= 7_000_000:
        level = "Платиновый"
    elif user.total_spent >= 3_000_000:
        level = "Золотой"
    elif user.total_spent >= 1_000_000:
        level = "Серебряный"

    await message.answer(
        f"Баланс: <b>{user.bonus_balance} баллов</b>\n"
        f"Текущий уровень: <b>{level}</b>\n"
        f"Всего покупок на сумму: <b>{user.total_spent:,} UZS</b>\n\n"
        f"100 баллов = 1 000 UZS скидки", parse_mode='HTML'
    )


@router.message(F.text == "Пригласить друга")
async def invite_friend(message: Message):
    user = await rq.get_user_reg(message.from_user.id)
    if not user:
        await message.answer("Сначала зарегистрируйтесь!")
        return

    if not user.referral_code:
        # Генерируем уникальный код
        code = f"REF{message.from_user.id:06d}"
        await rq.update_user(message.from_user.id, referral_code=code)
    else:
        code = user.referral_code

    await message.answer(
        "Пригласите друзей и получайте бонусы!\n\n"
        f"Ваш промокод: <code>{code}</code>\n\n"
        "Когда друг сделает первый заказ и укажет ваш промокод, "
        "вы получите 3000 бонусных баллов, а друг - 1000 баллов."
    )


@router.message(F.text == "Отследить заказ")
async def track_order(message: Message):
    await message.answer(
        "Введите номер вашего заказа или выберите из списка:",
        reply_markup=await get_user_orders_keyboard(message.from_user.id)
    )


async def get_user_orders_keyboard(user_id: int):
    user = await rq.get_user_reg(user_id)
    if not user:
        return None

    orders = await rq.get_user_orders(user.id)
    keyboard = InlineKeyboardBuilder()

    for order in orders:
        keyboard.add(InlineKeyboardButton(
            text=f"Заказ #{order.id} - {order.status}",
            callback_data=f"order_{order.id}"
        ))

    return keyboard.adjust(1).as_markup()