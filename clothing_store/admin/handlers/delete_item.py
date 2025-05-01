from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import clothing_store.database.requests as rq
from clothing_store.admin.state import DeleteItem


del_item_router = Router()


@del_item_router.callback_query(F.data.startswith('delete_item_'))
async def ask_delete_confirmation(callback: CallbackQuery, state: FSMContext):
    item_id = int(callback.data.split('_')[-1])
    await state.update_data(delete_item_id=item_id)
    await state.set_state(DeleteItem.confirm)
    await callback.message.answer("Вы действительно хотите удалить товар? Введите 'да' или 'нет'.")
    await callback.answer()


@del_item_router.message(DeleteItem.confirm)
async def confirm_delete(message: Message, state: FSMContext):
    user_response = message.text.strip().lower()
    data = await state.get_data()
    item_id = data.get("delete_item_id")

    if user_response == "да":
        await rq.delete_item(item_id)
        await message.answer("✅ Товар успешно удален!")
    elif user_response == "нет":
        await message.answer("❌ Удаление отменено.")
    else:
        await message.answer("Пожалуйста, введите 'да' или 'нет'.")
        return

    await state.clear()