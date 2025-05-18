import logging

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
import clothing_store.database.requests as rq
from clothing_store.users.bonus import BonusService
from clothing_store.users.keyboards import get_delivery_pickup_keyboard, get_transfer_delivery_keyboard
from clothing_store.admin.state import RegisterOrder, OrderStates
from aiogram.fsm.context import FSMContext
from aiogram.types import ReplyKeyboardRemove

payment_router = Router()


class FakeCallback:
    """Вспомогательный класс для эмуляции CallbackQuery"""

    def __init__(self, message: Message, data: str, bot: Bot):
        self.message = message
        self.from_user = message.from_user
        self.data = data
        self.id = "fake_callback_id"
        self.chat_instance = "fake_chat_instance"
        self.bot = bot

    async def answer(self, *args, **kwargs):
        """Эмуляция метода answer для CallbackQuery"""
        pass  # Можно добавить логирование или другую логику при необходимости


@payment_router.callback_query(F.data.startswith("installment_"))
async def choose_delivery_or_pickup(callback: CallbackQuery):
    item_id = _extract_id(callback.data)
    if item_id is None:
        await callback.answer("ID товара не найден", show_alert=True)
        return

    lang = await rq.get_user(callback.from_user.id)
    prompt = "Выберите способ получения:" if lang == "ru" else "Yetkazib berish turini tanlang:"
    kb = get_delivery_pickup_keyboard(lang, item_id)
    await _safe_edit(callback, prompt, kb)


@payment_router.callback_query(F.data.startswith("pay_card_"))
async def choose_transfer_delivery(callback: CallbackQuery):
    item_id = _extract_id(callback.data)
    if item_id is None:
        await callback.answer("ID товара не найден", show_alert=True)
        return

    lang = await rq.get_user(callback.from_user.id)
    prompt = "Выберите способ доставки:" if lang == "ru" else "Yetkazib berish usulini tanlang:"
    kb = get_transfer_delivery_keyboard(lang, item_id)
    await _safe_edit(callback, prompt, kb)


async def check_phone_and_process_order(callback: CallbackQuery, state: FSMContext, prefix: str, item_id: int):
    """Проверяет наличие телефона и либо запрашивает его, либо обрабатывает заказ"""
    user = await rq.get_user_reg(callback.from_user.id)
    if not user:
        await callback.answer("Ошибка: пользователь не найден", show_alert=True)
        return

    if not user.phone:
        # Запрашиваем телефон
        await state.set_state(OrderStates.waiting_for_phone)
        kb_phone = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Отправить номер", request_contact=True)]],
            resize_keyboard=True
        )
        lang = await rq.get_user(callback.from_user.id)
        text = "Для оформления заказа нужен ваш номер телефона:" if lang == "ru" else "Buyurtma uchun telefon raqamingiz kerak:"

        # Сохраняем данные для продолжения после получения телефона
        await state.update_data({
            "prefix": prefix,
            "item_id": item_id,
            "original_message_id": callback.message.message_id,
            "is_callback": True
        })

        await callback.message.answer(text, reply_markup=kb_phone)
        await callback.answer()
    else:
        # Телефон есть - обрабатываем заказ
        await _process_order(callback, prefix, item_id, user)


@payment_router.callback_query(
    F.data.startswith("delivery_") |
    F.data.startswith("pickup_") |
    F.data.startswith("yandex_") |
    F.data.startswith("courier_") |
    F.data.startswith("post_") |
    F.data.startswith("fitting_")
)
async def finalize_order(callback: CallbackQuery, state: FSMContext):
    prefix, item_id = _split_prefix_id(callback.data)
    await check_phone_and_process_order(callback, state, prefix, item_id)


@payment_router.message(OrderStates.waiting_for_phone, F.contact)
async def handle_phone_input(message: Message, state: FSMContext, bot: Bot):  # Add bot parameter
    """Обрабатывает ввод номера телефона и продолжает оформление заказа"""
    data = await state.get_data()
    phone = message.contact.phone_number

    # Сохраняем телефон и обновляем данные пользователя
    await rq.update_user(
        message.from_user.id,
        phone=phone,
        full_name=message.from_user.full_name,
        user_link=f"https://t.me/{message.from_user.username}" if message.from_user.username else None
    )
    user = await rq.get_user_reg(message.from_user.id)

    # Продолжаем обработку заказа
    prefix = data.get("prefix")
    item_id = data.get("item_id")
    if prefix and item_id:
        fake_callback = FakeCallback(message, f"{prefix}_{item_id}", bot)  # Pass bot instance
        await _process_order(fake_callback, prefix, item_id, user)

    await state.clear()


async def _process_order(callback: CallbackQuery, prefix: str, item_id: int, user):
    """Основная логика обработки заказа"""
    payment = "Наличные" if prefix in {"delivery", "pickup"} else "Перевод на карту"
    lang = await rq.get_user(callback.from_user.id)
    item = await rq.get_item(item_id)

    item_label = f"{item.name_ru} (Id {item.id})" if item else f"ID {item_id}"

    delivery_map = {
        "ru": {
            "delivery": "Доставка",
            "pickup": "Самовывоз",
            "yandex": "Яндекс/Уклон",
            "courier": "Курьер",
            "post": "Почта",
            "fitting": "Доставка с примеркой",
        },
        "uz": {
            "delivery": "Yetkazib berish",
            "pickup": "O'zingiz olib ketish",
            "yandex": "Yandex/Uklon",
            "courier": "Kuryer",
            "post": "Pochta",
            "fitting": "O'lchab ko'rish bilan",
        }
    }
    delivery_label = delivery_map.get(lang, delivery_map["ru"]).get(prefix, prefix)

    # Обновляем данные пользователя перед созданием заказа
    if not user.user_link and callback.from_user.username:
        await rq.update_user(
            callback.from_user.id,
            user_link=f"https://t.me/{callback.from_user.username}"
        )

    # Создаем заказ
    order = await rq.add_order(
        photo=[],
        shipping_method=delivery_label,
        user_id=user.id,
        item_id=item.id if item else None,
        quantity=1,
        total_price=item.price if item else None,
    )

    # Формируем сообщение администратору с полными данными
    admin_text = (
        "⚠️ <b>Новый заказ</b>\n"
        f"Номер заказа: №<code>{order.id}</code>\n"
        f"Имя пользователя: {user.full_name or user.user_name}\n"
        f"Ссылка на пользователя: {user.user_link or 'не указана'}\n"
        f"ID пользователя: <code>{user.tg_id}</code>\n"
        f"Телефон: {user.phone or 'не указан'}\n"
        f"Товар: {item_label}\n"
        f"Способ получения: {delivery_label}\n"
        f"Оплата: {payment}"
    )

    try:
        await callback.bot.send_message(661394290, admin_text, parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка отправки уведомления админу: {e}")

    confirm = (
        "Спасибо! Заказ принят, скоро свяжемся." if lang == "ru"
        else "Rahmat! Buyurtma qabul qilindi, tez orada aloqaga chiqamiz."
    )
    await _safe_edit(callback, confirm, None)


def _extract_id(data: str) -> int | None:
    """Извлекает ID из callback_data"""
    tail = data.split("_")[-1]
    return int(tail) if tail.isdigit() else None


def _split_prefix_id(data: str) -> tuple[str, int | None]:
    """Разделяет callback_data на префикс и ID"""
    prefix, _, tail = data.partition("_")
    return prefix, int(tail) if tail.isdigit() else None


async def _safe_edit(callback: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None):
    """Безопасное редактирование сообщения"""
    try:
        # Try to edit the message text first
        await callback.message.edit_text(text, reply_markup=kb)
    except Exception as e:
        try:
            # If that fails, try editing the caption (for media messages)
            await callback.message.edit_caption(text, reply_markup=kb)
        except Exception as e:
            try:
                # If all else fails, just send a new message
                await callback.message.answer(text, reply_markup=kb)
            except Exception as e:
                logging.error(f"Failed to edit or send message: {e}")
    finally:
        await callback.answer()