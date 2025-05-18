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
    waiting_order_id = State()
    quantity = State()
    total_price = State()
    deposit = State()
    status = State()
    confirmation = State()


class UpdateOrderStatus(StatesGroup):
    """
    Состояния для изменения статуса заказа администратором
    """
    select_order = State()
    select_status = State()
    confirm_delivery = State()
    add_comment = State()


class OrderStates(StatesGroup):
    waiting_for_phone = State()