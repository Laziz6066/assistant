from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
import clothing_store.database.requests as rq
import clothing_store.admin.a_keyboards as admin_kb
from clothing_store.admin.state import UpdateItem


upd_item_router = Router()


@upd_item_router.callback_query(F.data.startswith('update_item_'))
async def start_update_item(callback: CallbackQuery, state: FSMContext):
    # Извлекаем id товара из callback_data
    item_id = int(callback.data.split('_')[-1])
    # Получаем данные товара
    item = await rq.get_item_for_update(item_id)
    if not item:
        await callback.message.answer("Ошибка: Товар не найден.")
        return
    # Сохраняем в состоянии как id товара и текущие значения
    await state.update_data(
        update_item_id=item_id,
        current_name_ru=item.name_ru,
        current_name_uz=item.name_uz,
        current_description_ru=item.description_ru,
        current_description_uz=item.description_uz,
        current_price=item.price
    )
    await state.set_state(UpdateItem.name_ru)
    await callback.message.answer(
        f"Текущее название товара (на русском): {item.name_ru}\n"
        "Введите новое название товара (на русском):",
        reply_markup=ReplyKeyboardRemove()
    )
    await callback.answer()


@upd_item_router.message(UpdateItem.name_ru)
async def update_item_name_ru(message: Message, state: FSMContext):
    await state.update_data(name_ru=message.text)
    data = await state.get_data()
    await state.set_state(UpdateItem.name_uz)
    await message.answer(
        f"Текущее название товара (на узбекском): {data.get('current_name_uz')}\n"
        "Введите новое название товара (на узбекском):"
    )


@upd_item_router.message(UpdateItem.name_uz)
async def update_item_name_uz(message: Message, state: FSMContext):
    await state.update_data(name_uz=message.text)
    data = await state.get_data()
    await state.set_state(UpdateItem.description_ru)
    await message.answer(
        f"Текущее описание товара (на русском): {data.get('current_description_ru')}\n"
        "Введите новое описание товара (на русском):"
    )


@upd_item_router.message(UpdateItem.description_ru)
async def update_item_description_ru(message: Message, state: FSMContext):
    await state.update_data(description_ru=message.text)
    data = await state.get_data()
    await state.set_state(UpdateItem.description_uz)
    await message.answer(
        f"Текущее описание товара (на узбекском): {data.get('current_description_uz')}\n"
        "Введите новое описание товара (на узбекском):"
    )


@upd_item_router.message(UpdateItem.description_uz)
async def update_item_description_uz(message: Message, state: FSMContext):
    await state.update_data(description_uz=message.text)
    data = await state.get_data()
    await state.set_state(UpdateItem.price)
    await message.answer(
        f"Текущая цена товара: {data.get('current_price')}\n"
        "Введите новую цену товара (только число):"
    )


@upd_item_router.message(UpdateItem.price)
async def update_item_price(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите корректную цену (только число).")
        return

    await state.update_data(price=int(message.text))
    data = await state.get_data()
    item_id = data.get("update_item_id")

    await rq.update_item(
        item_id=item_id,
        name_ru=data['name_ru'],
        name_uz=data['name_uz'],
        description_ru=data['description_ru'],
        description_uz=data['description_uz'],
        price=data['price']
    )
    main_menu = await admin_kb.admin_keyboard(message.from_user.id)
    await state.clear()
    await message.answer("✅ Товар успешно изменён!", reply_markup=main_menu)

