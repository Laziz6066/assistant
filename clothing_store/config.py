from dotenv import load_dotenv
import os


load_dotenv()
ADMINS = list(map(int, os.getenv('ADMINS', '').split(','))) if os.getenv('ADMINS') else []

main_photo = "https://sun9-77.userapi.com/KWoCJ3Smj_J7QyoEci1kEAU2Lyp9YOHvmI6DnA/SXtJSQwIFKw.jpg"

text_main_menu_key = {
    'ru': {
        'stock': 'Товары в наличии',
        'order': 'На заказ',
        'bonuses': 'Мои баллы',
        'account': 'Личный кабинет',
        'support': 'Поддержка',
        'change_lang': 'Сменить язык',
        'about': 'О нас',
        'tracking': "Отследить заказ",
    },
    'uz': {
        'stock': 'Bor mahsulotlar',
        'order': 'Buyurtma',
        'bonuses': 'Mening ballarim',
        'account': 'Shaxsiy kabinet',
        'support': "Qo'llab-quvvatlash",
        'change_lang': "Tilni o'zgartirish",
        'about': 'Biz haqimizda',
        'tracking': "Buyurtmani kuzatib boring",
    }
}

text_get_contacts = {
    'ru': {
        'service': 'Сервисный центр',
        'manager': 'Менеджер',
        'menu': 'Главное меню',
    },
    'uz': {
        'service': "Xizmat ko'rsatish markazi",
        'manager': 'Menejer',
        'menu': 'Asosiy menyu',
    }
}

text_contacts = {
    'ru': "По всем вопросам:\nТелефон: <b>+998932800019</b>\nТг: <b>@jully_admin</b>.",
    'uz': "Barcha savollar bo'yicha:\nTelefon: <b>+998932800019</b>\nTg: <b>@jully_admin</b>."
}

text_main_menu = {
    'ru': "Можно написать приветственный текст и отправить фото.",
    'uz': "Siz xush kelibsiz matnni yozishingiz va fotosuratni yuborishingiz mumkin."
}

choice_category = {
    'ru': "Выберите категорию:",
    'uz': "Toifani tanlang:"
}

choice_language = {
    'ru': "Сменить язык",
    'uz': "Tilni o'zgartirish"
}

installment = {
    'ru': "Выберите срок рассрочки:",
    'uz': "To'lov muddatini tanlang:",
}

order = {
    'ru': "Для того чтобы заказать отправьте фото товара.",
    'uz': "Buyurtma berish uchun mahsulot fotosuratini yuboring."
}