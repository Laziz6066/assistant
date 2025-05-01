from aiogram import Router, F
from clothing_store.database.requests import add_category, delete_category_by_name
from aiogram.types import Message
import clothing_store.users.keyboards as kb
from clothing_store.admin.state import AddCategory, DeleteCategory
from aiogram.fsm.context import FSMContext
from clothing_store.config import ADMINS

category_router = Router()


@category_router.message(F.text == 'Добавить категорию')
async def start_add_category(message: Message, state: FSMContext):
    if message.from_user.id in ADMINS:
        await state.set_state(AddCategory.name_uz)
        await message.answer("Введите название новой категории (на узбекском):")
    else:
        await message.answer('У вас нет доступа !!!')


@category_router.message(AddCategory.name_uz)
async def add_category_name_ru(message: Message, state: FSMContext):
    category_name_uz = message.text.strip()
    await state.update_data(name_uz=category_name_uz)

    if len(category_name_uz) > 500:
        await message.answer("Название категории слишком длинное. Введите до 500 символов.")
        return

    await state.set_state(AddCategory.name_ru)
    await message.answer("Введите название новой категории (на русском):")


@category_router.message(AddCategory.name_ru)
async def save_category(message: Message, state: FSMContext):
    category_name_ru = message.text.strip()
    await state.update_data(name_ru=category_name_ru)

    if len(category_name_ru) > 500:
        await message.answer("Название категории слишком длинное. Введите до 500 символов.")
        return
    data = await state.get_data()

    await add_category(name_ru=data['name_ru'], name_uz=data['name_uz'])
    await state.clear()
    keyboard = await kb.get_main_keyboard(message.from_user.id)
    await message.answer(f"Категория '{category_name_ru[0:7]}...' успешно добавлена!", reply_markup=keyboard)


@category_router.message(F.text == 'Удалить категорию')
async def start_delete_category(message: Message, state: FSMContext):
    if message.from_user.id in ADMINS:
        await state.set_state(DeleteCategory.waiting_for_name)
        await message.answer("Введите название категории для удаления:")
    else:
        await message.answer("У вас нет доступа.")

@category_router.message(DeleteCategory.waiting_for_name)
async def process_delete_category(message: Message, state: FSMContext):
    category_name = message.text.strip()
    await delete_category_by_name(category_name)
    await message.answer(f"Категория '{category_name}' успешно удалена!")
    await state.clear()