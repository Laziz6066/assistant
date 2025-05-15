from aiogram.fsm.state import StatesGroup, State


class AddCategory(StatesGroup):
    name_uz = State()
    name_ru = State()


class AddItem(StatesGroup):
    name_uz = State()
    name_ru = State()
    description_uz = State()
    description_ru = State()
    price = State()
    photo = State()
    category = State()
    brand = State()
    subcategory = State()


class DeleteCategory(StatesGroup):
    waiting_for_name = State()


class DeleteItem(StatesGroup):
    confirm = State()


class UpdateItem(StatesGroup):
    name_ru = State()
    name_uz = State()
    description_ru = State()
    description_uz = State()
    price = State()


class AddOrder(StatesGroup):
    photo = State()
    shipping_method = State()


class RegisterOrder(StatesGroup):
    full_name = State()
    phone = State()
    address = State()


class PersonalAccount(StatesGroup):
    full_name = State()
    phone = State()
    date_of_birth = State()


class SetPaidSG(StatesGroup):
    quantity = State()
    total_price = State()
    deposit = State()
    status = State()
    waiting_order_id = State()
    confirmation = State()
