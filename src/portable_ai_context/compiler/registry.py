from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import re
from typing import Any

from portable_ai_context.errors import CompilerError
from .base import CompilerBackend
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


def _openai_compatible_factory(config: BackendConfig) -> CompilerBackend:
    api_base = config.api_base
    if not isinstance(api_base, str) or not api_base.strip():
        raise CompilerError("openai-compatible backend requires --api-base")
    if not isinstance(config.timeout, int) or isinstance(config.timeout, bool) or config.timeout <= 0:
        raise CompilerError("compiler backend timeout must be a positive integer")
    if not isinstance(config.api_key_env, str) or not _ENV_NAME_RE.fullmatch(config.api_key_env):
        raise CompilerError("compiler API-key environment variable name is invalid")

    api_key = config.environment.get(config.api_key_env)
    if not isinstance(api_key, str) or not api_key:
        raise CompilerError(
            f"environment variable {config.api_key_env!r} is not set"
        )
    return OpenAICompatibleBackend(
        api_base=api_base,
        api_key=api_key,
        timeout=config.timeout,
    )


register_backend("openai-compatible", _openai_compatible_factory)
