from __future__ import annotations

from typing import Any


CANONICAL_ROLE_ORDER = ("user", "assistant")
CANONICAL_ROLES = frozenset(CANONICAL_ROLE_ORDER)
CANONICAL_MESSAGE_FIELD_ORDER = ("role", "text")
CANONICAL_MESSAGE_FIELDS = frozenset(CANONICAL_MESSAGE_FIELD_ORDER)


def canonical_message_record(role: str, text: str) -> dict[str, Any]:
    """Build the existing narrow canonical JSONL record shape.

    Validation remains the responsibility of conformance/readers. Keeping this
    helper tiny prevents exporter field drift without turning tolerant source
    adapters into strict canonical validators.
    """

    return {"role": role, "text": text}
