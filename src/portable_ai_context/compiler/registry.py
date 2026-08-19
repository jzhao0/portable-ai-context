from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import re
from typing import Any

from portable_ai_context.errors import CompilerError
from .anthropic import (
    AnthropicBackend,
    DEFAULT_ANTHROPIC_API_BASE,
    DEFAULT_ANTHROPIC_MAX_TOKENS,
)
from .base import CompilerBackend
from .gemini import (
    DEFAULT_GEMINI_API_BASE,
    DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
    GeminiBackend,
)
from .ollama import (
    DEFAULT_OLLAMA_API_BASE,
    DEFAULT_OLLAMA_NUM_PREDICT,
    OllamaBackend,
)
from .openai_compatible import OpenAICompatibleBackend


_BACKEND_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(slots=True, frozen=True)
class BackendConfig:
    """Provider-construction inputs shared by the alpha CLI boundary.

    `environment` and `options` are intentionally excluded from repr so normal
    debugging never expands environment secrets or future provider options.
    """

    api_base: str | None = None
    api_key_env: str = "PAIC_API_KEY"
    timeout: int = 300
    environment: Mapping[str, str] = field(default_factory=dict, repr=False)
    options: Mapping[str, Any] = field(default_factory=dict, repr=False)


BackendFactory = Callable[[BackendConfig], CompilerBackend]
_BACKENDS: dict[str, BackendFactory] = {}


def _validate_backend_name(name: str) -> str:
    if not isinstance(name, str) or not _BACKEND_NAME_RE.fullmatch(name):
        raise ValueError("compiler backend name must be a safe lowercase identifier")
    return name


def register_backend(name: str, factory: BackendFactory) -> None:
    safe_name = _validate_backend_name(name)
    if not callable(factory):
        raise TypeError("compiler backend factory must be callable")
    if safe_name in _BACKENDS:
        raise ValueError(f"compiler backend is already registered: {safe_name}")
    _BACKENDS[safe_name] = factory


def available_backends() -> tuple[str, ...]:
    return tuple(sorted(_BACKENDS))


def create_backend(name: str, config: BackendConfig) -> CompilerBackend:
    try:
        safe_name = _validate_backend_name(name)
    except ValueError as exc:
        available = ", ".join(available_backends()) or "<none>"
        raise CompilerError(
            f"unknown compiler backend; available backends: {available}"
        ) from exc

    factory = _BACKENDS.get(safe_name)
    if factory is None:
        available = ", ".join(available_backends()) or "<none>"
        raise CompilerError(
            f"unknown compiler backend; available backends: {available}"
        )
    try:
        backend = factory(config)
    except CompilerError:
        raise
    except Exception as exc:
        raise CompilerError("compiler backend construction failed") from exc

    if not callable(getattr(backend, "complete", None)):
        raise CompilerError("compiler backend factory returned an invalid backend")
    return backend


def _validate_env_name(value: Any) -> str:
    if not isinstance(value, str) or not _ENV_NAME_RE.fullmatch(value):
        raise CompilerError("compiler API-key environment variable name is invalid")
    return value


def _validate_api_key_env(config: BackendConfig) -> str:
    return _validate_env_name(config.api_key_env)


def _resolve_api_key(config: BackendConfig) -> str:
    env_name = _validate_api_key_env(config)
    api_key = config.environment.get(env_name)
    if not isinstance(api_key, str) or not api_key:
        raise CompilerError(f"environment variable {env_name!r} is not set")
    return api_key


def _validate_timeout(config: BackendConfig) -> int:
    if not isinstance(config.timeout, int) or isinstance(config.timeout, bool) or config.timeout <= 0:
        raise CompilerError("compiler backend timeout must be a positive integer")
    return config.timeout


def _openai_compatible_factory(config: BackendConfig) -> CompilerBackend:
    api_base = config.api_base
    if not isinstance(api_base, str) or not api_base.strip():
        raise CompilerError("openai-compatible backend requires --api-base")
    return OpenAICompatibleBackend(
        api_base=api_base,
        api_key=_resolve_api_key(config),
        timeout=_validate_timeout(config),
    )


def _anthropic_factory(config: BackendConfig) -> CompilerBackend:
    api_base = config.api_base if config.api_base is not None else DEFAULT_ANTHROPIC_API_BASE
    if not isinstance(api_base, str) or not api_base.strip():
        raise CompilerError("anthropic backend API base is invalid")

    max_tokens = config.options.get("anthropic_max_tokens", DEFAULT_ANTHROPIC_MAX_TOKENS)
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens <= 0:
        raise CompilerError("anthropic max_tokens must be a positive integer")

    return AnthropicBackend(
        api_base=api_base,
        api_key=_resolve_api_key(config),
        max_tokens=max_tokens,
        timeout=_validate_timeout(config),
    )


def _gemini_factory(config: BackendConfig) -> CompilerBackend:
    api_base = config.api_base if config.api_base is not None else DEFAULT_GEMINI_API_BASE
    if not isinstance(api_base, str) or not api_base.strip():
        raise CompilerError("gemini backend API base is invalid")

    max_output_tokens = config.options.get(
        "gemini_max_output_tokens", DEFAULT_GEMINI_MAX_OUTPUT_TOKENS
    )
    if (
        not isinstance(max_output_tokens, int)
        or isinstance(max_output_tokens, bool)
        or max_output_tokens <= 0
    ):
        raise CompilerError("gemini maxOutputTokens must be a positive integer")

    return GeminiBackend(
        api_base=api_base,
        api_key=_resolve_api_key(config),
        max_output_tokens=max_output_tokens,
        timeout=_validate_timeout(config),
    )


def _ollama_factory(config: BackendConfig) -> CompilerBackend:
    api_base = config.api_base if config.api_base is not None else DEFAULT_OLLAMA_API_BASE
    if not isinstance(api_base, str) or not api_base.strip():
        raise CompilerError("ollama backend API base is invalid")

    num_predict = config.options.get("ollama_num_predict", DEFAULT_OLLAMA_NUM_PREDICT)
    if not isinstance(num_predict, int) or isinstance(num_predict, bool) or num_predict <= 0:
        raise CompilerError("ollama num_predict must be a positive integer")

    api_key: str | None = None
    api_key_env = config.options.get("ollama_api_key_env")
    if api_key_env is not None:
        env_name = _validate_env_name(api_key_env)
        resolved = config.environment.get(env_name)
        if not isinstance(resolved, str) or not resolved:
            raise CompilerError(f"environment variable {env_name!r} is not set")
        api_key = resolved

    return OllamaBackend(
        api_base=api_base,
        api_key=api_key,
        num_predict=num_predict,
        timeout=_validate_timeout(config),
    )


register_backend("anthropic", _anthropic_factory)
register_backend("gemini", _gemini_factory)
register_backend("ollama", _ollama_factory)
register_backend("openai-compatible", _openai_compatible_factory)
