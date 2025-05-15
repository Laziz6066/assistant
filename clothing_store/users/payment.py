from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.types import InlineKeyboardMarkup
import clothing_store.database.requests as rq
from clothing_store.users.keyboards import get_delivery_pickup_keyboard, get_transfer_delivery_keyboard

payment_router = Router()


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

# =============== Оплата переводом на карту ===============
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

# ================= Финальный выбор доставки =================
@payment_router.callback_query(
    F.data.startswith("delivery_") |
    F.data.startswith("pickup_") |
    F.data.startswith("yandex_") |
    F.data.startswith("courier_") |
    F.data.startswith("post_") |
    F.data.startswith("fitting_")
)
async def finalize_order(callback: CallbackQuery):
    prefix, item_id = _split_prefix_id(callback.data)

    # Определяем способ оплаты по сохранённому состоянию (наличные / перевод)
    payment = "Наличные" if prefix in {"delivery", "pickup"} else "Перевод на карту"

    lang = await rq.get_user(callback.from_user.id)
    item = await rq.get_item(item_id)

    item_label = (
        f"{item.name_ru} (Id {item.id})" if item else f"ID {item_id}"
    )

    delivery_map_ru = {
        "delivery": "Доставка",
        "pickup": "Самовывоз",
        "yandex": "Яндекс/Уклон",
        "courier": "Курьер",
        "post": "Почта",
        "fitting": "Доставка с примеркой",
    }
    delivery_label = delivery_map_ru.get(prefix, prefix)

    user = await rq.get_user_reg(callback.from_user.id)

    admin_text = (
        "⚠️ <b>Новый заказ</b>\n"
        f"Имя пользователя: {user.full_name}\n"
        f"Ссылка на пользователя: {user.user_link or '—'}\n"
        f"ID пользователя: <code>{user.tg_id}</code>\n"
        f"Телефон: {user.phone}\n"
        f"Товар: {item_label}\n"
        f"Способ получения: {delivery_label}\n"
        f"Оплата: {payment}\n"
    )


    try:
        await callback.bot.send_message(661394290, admin_text, parse_mode="HTML")
    except Exception:
        pass

    # Подтверждаем пользователю
    confirm = (
        "Спасибо! Заказ принят, скоро свяжемся." if lang == "ru" else
        "Rahmat! Buyurtma qabul qilindi, tez orada aloqaga chiqamiz."
    )
    await _safe_edit(callback, confirm, None)

# ================= Вспомогательные =================

def _extract_id(data: str) -> int | None:
    """Вернуть число после последнего '_' если оно есть."""
    tail = data.split("_")[-1]
    return int(tail) if tail.isdigit() else None


def _split_prefix_id(data: str):
    """Разделить callback-data на prefix и item_id."""
    prefix, _, tail = data.partition("_")
    return prefix, int(tail) if tail.isdigit() else None


async def _safe_edit(callback: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None):
    edited = False
    try:
        await callback.message.edit_text(text, reply_markup=kb)
        edited = True
    except Exception:
        pass
    if not edited:
        try:
            await callback.message.edit_caption(text, reply_markup=kb)
            edited = True
        except Exception:
            pass
    if not edited:
        await callback.message.edit_reply_markup(reply_markup=kb)

    await callback.answer()

