from __future__ import annotations

import json
from pathlib import Path

from portable_ai_context.canonical_contract import CANONICAL_ROLES
from portable_ai_context.errors import ParseError
from portable_ai_context.models import Conversation, Message, SourceInfo
from portable_ai_context.utils import source_fingerprint


def can_load(source: str) -> bool:
    return Path(source).suffix.lower() in {".jsonl", ".ndjson"}


def load(source: str, text: str) -> Conversation:
    messages: list[Message] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ParseError(f"JSONL line {lineno} is invalid") from exc
        if not isinstance(obj, dict):
            continue
        role = obj.get("role")
        body = obj.get("text")
        if role in CANONICAL_ROLES and isinstance(body, str) and body.strip():
            messages.append(Message(role=role, text=body, index=len(messages)))

    if not messages:
        raise ParseError("JSONL contains no canonical user/assistant messages")

    return Conversation(
        title="",
        messages=messages,
        source=SourceInfo(
            kind="jsonl",
            locator=str(Path(source)),
            fingerprint=source_fingerprint(text),
        ),
    )
