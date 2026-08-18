from __future__ import annotations

from typing import Protocol


class CompilerBackend(Protocol):
    def complete(self, *, model: str, system: str, user: str, stage: str) -> str: ...
