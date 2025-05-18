from decimal import Decimal
from clothing_store.database.models import BonusTransaction, async_session, Order, User
from clothing_store.database import requests as rq
from sqlalchemy import select, update, delete


class BonusService:

    @staticmethod
    async def calculate_bonus(user_id: int, order_amount: int) -> int:
        user = await rq.get_user_by_pk(user_id)
        if not user:
            return 0

        total_spent = user.total_spent + order_amount

        if total_spent >= 7_000_000:
            return int(order_amount * 0.05)  # 5% for Platinum
        elif total_spent >= 3_000_000:
            return int(order_amount * 0.03)  # 3% for Gold
        elif total_spent >= 1_000_000:
            return int(order_amount * 0.01)  # 1% for Silver
        else:
            return order_amount // 1000  # 1 point per 1000 сум for Newbie

    @staticmethod
    async def check_and_apply_bonuses(order_id: int):
        async with async_session() as session:
            order = await session.get(Order, order_id)

            if not order or not order.is_delivered or order.is_bonus_calculated:
                return

            if order.total_price:
                bonus_amount = await BonusService.calculate_bonus(
                    order.user,  # Используем существующее поле user
                    order.total_price
                )
                await BonusService.add_bonus(
                    order.user,
                    bonus_amount,
                    f"Бонусы за заказ #{order.id}",
                    order.id
                )

                await BonusService.add_bonus(
                    order.user,  # Используем существующее поле user
                    bonus_amount,
                    f"Бонусы за заказ #{order.id}",
                    order.id
                )

            order.is_bonus_calculated = True
            await session.commit()

    @staticmethod
    async def add_bonus(user_id: int, amount: int, description: str, order_id: int | None = None):
        async with async_session() as session:
            # Add transaction
            transaction = BonusTransaction(
                user_id=user_id,
                amount=amount,
                description=description,
                order_id=order_id
            )
            session.add(transaction)

            # Update user balance
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(bonus_balance=User.bonus_balance + amount)
            )
            await session.commit()

    @staticmethod
    async def apply_referral_bonus(new_user_id: int, referrer_code: str):
        async with async_session() as session:
            # Find referrer
            referrer = await session.execute(
                select(User).where(User.referral_code == referrer_code)
            )
            referrer = referrer.scalar_one_or_none()

            if not referrer:
                return

            # Add bonus to new user
            await BonusService.add_bonus(
                new_user_id,
                1000,
                f"Бонус за использование промокода {referrer_code}"
            )

            # Add bonus to referrer
            await BonusService.add_bonus(
                referrer.id,
                3000,
                f"Реферальный бонус за пользователя {new_user_id}"
            )