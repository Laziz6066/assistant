from __future__ import annotations
from abc import ABC, abstractmethod


class Activator(ABC):
    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
