import os
import asyncio
import logging
from aiogram import Bot, Dispatcher
from clothing_store.admin.handlers.admin_orders import admin_order_router
from clothing_store.admin.handlers.confirmation import status_router
from clothing_store.users.account import account_router
from clothing_store.users.handlers import router
from clothing_store.admin.handlers.admin_menu import admin_router
from clothing_store.admin.handlers.add_item import add_item_router
from clothing_store.admin.handlers.delete_item import del_item_router
from clothing_store.admin.handlers.update_item import upd_item_router
from clothing_store.admin.handlers.category import category_router
from clothing_store.users.orders import order_router
from clothing_store.database.models import async_main
from dotenv import load_dotenv

from clothing_store.users.payment import payment_router


async def main():
    await async_main()

    load_dotenv()

    bot = Bot(token=os.getenv('TOKEN'))
    dp = Dispatcher()

    dp.include_router(router)
    dp.include_router(admin_router)
    dp.include_router(add_item_router)
    dp.include_router(del_item_router)
    dp.include_router(upd_item_router)
    dp.include_router(category_router)
    dp.include_router(order_router)
    dp.include_router(account_router)
    dp.include_router(payment_router)
    dp.include_router(status_router)
    dp.include_router(admin_order_router)
    
    await dp.start_polling(bot)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Exit')
