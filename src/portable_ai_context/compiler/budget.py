from __future__ import annotations

from dataclasses import asdict, dataclass, field
import importlib
import math
import re
from typing import Any, Callable, Protocol

from portable_ai_context.errors import CompilerError


PROFILE_BUDGETS = {
    "lite": 4_000,
    "standard": 16_000,
    "full": 64_000,
}

_SAFE_TIKTOKEN_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


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
class TiktokenTokenCounter:
    """Optional exact raw-text counter backed by OpenAI's tiktoken.

    Exactness is deliberately narrow: this counts the plain text passed to
    ``count`` under the resolved tiktoken encoding. It does not model provider
    request framing, tool/image tokens, or provider-added system tokens.
    """

    encoding_name: str | None = None
    model: str | None = None
    name: str = field(init=False)
    exact: bool = field(default=True, init=False)
    _encoding: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.encoding_name is not None:
            if (
                not isinstance(self.encoding_name, str)
                or not _SAFE_TIKTOKEN_NAME_RE.fullmatch(self.encoding_name)
            ):
                raise CompilerError("tiktoken encoding identifier is invalid")
        if self.model is not None:
            if (
                not isinstance(self.model, str)
                or not _SAFE_TIKTOKEN_NAME_RE.fullmatch(self.model)
            ):
                raise CompilerError("tiktoken model identifier is invalid")
        if self.encoding_name is None and self.model is None:
            raise CompilerError("tiktoken token counter requires a model or encoding")

        try:
            tiktoken = importlib.import_module("tiktoken")
        except ImportError as exc:
            raise CompilerError(
                "tiktoken token counter is unavailable; install portable-ai-context[tokenizers]"
            ) from exc

        if self.encoding_name is not None:
            try:
                encoding = tiktoken.get_encoding(self.encoding_name)
            except Exception as exc:
                raise CompilerError("tiktoken encoding is not available") from exc
        else:
            try:
                encoding = tiktoken.encoding_for_model(self.model)
            except KeyError as exc:
                raise CompilerError(
                    "tiktoken does not recognize the model; supply --tiktoken-encoding"
                ) from exc
            except Exception as exc:
                raise CompilerError("tiktoken model lookup failed") from exc

        resolved_name = getattr(encoding, "name", None)
        if not isinstance(resolved_name, str) or not _SAFE_TIKTOKEN_NAME_RE.fullmatch(
            resolved_name
        ):
            raise CompilerError("tiktoken returned an invalid encoding")
        encode_ordinary = getattr(encoding, "encode_ordinary", None)
        if not callable(encode_ordinary):
            raise CompilerError("tiktoken returned an invalid encoding")

        self._encoding = encoding
        self.name = f"tiktoken:{resolved_name}"

    def count(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError("token counter input must be text")
        try:
            return len(self._encoding.encode_ordinary(text))
        except Exception as exc:
            raise CompilerError("tiktoken token counting failed") from exc


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
