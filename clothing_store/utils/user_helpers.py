from __future__ import annotations
from typing import Sequence, List


ORDER_REQUIRED:   tuple[str, ...] = ("full_name", "phone", "address")
ACCOUNT_REQUIRED: tuple[str, ...] = ("full_name", "phone", "date_of_birth")


def get_missing_fields(user, required: Sequence[str]) -> List[str]:
    """
    Вернуть список полей из *required*, которые у пользователя ещё пустые.
    Пустым считается None или пустая строка.
    """
    return [field for field in required if not getattr(user, field)]