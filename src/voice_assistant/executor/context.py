from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from voice_assistant.config import AppConfig


@dataclass
class ExecutorContext:
    config: AppConfig
    platform_ops: object
    mode_store: Optional[object] = None  # ModeStore | None — avoid circular import

    def resolve_app(self, name: str) -> str:
        return self.config.app_aliases.get(name.strip().lower(), name.strip())

    def resolve_path(self, name: str) -> str:
        return self.config.path_aliases.get(name.strip().lower(), name.strip())

    def resolve_bookmark(self, name: str) -> str | None:
        return self.config.bookmarks.get(name.strip().lower())
