from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Callable, Protocol


PROFILE_BUDGETS = {
    "lite": 4_000,
    "standard": 16_000,
    "full": 64_000,
}


class TokenCounter(Protocol):
    name: str
    exact: bool

    def count(self, text: str) -> int: ...


@dataclass(slots=True)
class CharacterTokenCounter:
    """Dependency-free token estimator used when no exact tokenizer is available."""

    chars_per_token: float = 4.0
    name: str = "character_estimate"
    exact: bool = False

    def __post_init__(self) -> None:
        if self.chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")

    def count(self, text: str) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text) / self.chars_per_token))


@dataclass(slots=True)
class CallableTokenCounter:
    """Adapter for an injected exact or estimated tokenizer callable."""

    fn: Callable[[str], int]
    name: str
    exact: bool = True

    def count(self, text: str) -> int:
        value = int(self.fn(text))
        if value < 0:
            raise ValueError("token counter returned a negative value")
        return value


@dataclass(slots=True)
class CompilationReport:
    tokenizer: str
    tokenizer_exact: bool
    profile: str | None
    budget_tokens: int | None
    source_token_estimate: int
    output_token_estimate: int
    compression_ratio: float | None
    budget_overrun_tokens: int
    budget_met: bool | None
    budget_reduction_applied: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_budget(*, budget_tokens: int | None = None, profile: str | None = None) -> tuple[int | None, str | None]:
    if budget_tokens is not None and profile is not None:
        raise ValueError("budget_tokens and profile are mutually exclusive")
    if budget_tokens is not None:
        if budget_tokens <= 0:
            raise ValueError("budget_tokens must be positive")
        return budget_tokens, None
    if profile is None:
        return None, None
    normalized = profile.strip().lower()
    if normalized not in PROFILE_BUDGETS:
        raise ValueError(f"unknown budget profile: {profile}")
    return PROFILE_BUDGETS[normalized], normalized
