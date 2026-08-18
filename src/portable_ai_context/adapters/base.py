from __future__ import annotations

from typing import Protocol

from portable_ai_context.models import Conversation


class Adapter(Protocol):
    name: str

    def can_load(self, source: str, text: str | None = None) -> bool: ...
    def load(self, source: str, text: str | None = None) -> Conversation: ...
