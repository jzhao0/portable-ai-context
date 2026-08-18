from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from portable_ai_context.errors import ParseError
from portable_ai_context.models import Conversation, Message, SnapshotInfo, SourceInfo
from portable_ai_context.privacy import inspect_raw_text
from portable_ai_context.utils import source_fingerprint


ROLE_MAP = {
    "human": "user",
    "user": "user",
    "assistant": "assistant",
}


def _is_conversation_record(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("chat_messages"), list)


def _conversation_candidates(value: Any) -> list[dict[str, Any]]:
    if _is_conversation_record(value):
        return [value]
    if isinstance(value, list):
        return [item for item in value if _is_conversation_record(item)]
    if isinstance(value, dict) and isinstance(value.get("conversations"), list):
        return [item for item in value["conversations"] if _is_conversation_record(item)]
    return []


def can_load(text: str) -> bool:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return False
    return bool(_conversation_candidates(value))


def _select_conversation(value: Any) -> dict[str, Any]:
    candidates = _conversation_candidates(value)
    if not candidates:
        raise ParseError("Claude JSON contains no supported conversation record")
    if len(candidates) != 1:
        raise ParseError(
            "Claude JSON contains multiple conversation records; "
            "the alpha adapter accepts one conversation record per input file"
        )
    return candidates[0]


def _timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def _content_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, list):
        return ""

    parts: list[str] = []
    for block in value:
        if isinstance(block, str):
            text = block.strip()
            if text:
                parts.append(text)
            continue
        if not isinstance(block, dict):
            continue
        if block.get("type") not in {None, "text"}:
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n".join(parts).strip()


def _message_text(raw: dict[str, Any]) -> str:
    text = raw.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return _content_text(raw.get("content"))


def extract_messages(conversation: dict[str, Any]) -> list[Message]:
    out: list[Message] = []
    for raw in conversation.get("chat_messages", []):
        if not isinstance(raw, dict):
            continue
        sender = raw.get("sender")
        role = ROLE_MAP.get(sender) if isinstance(sender, str) else None
        if role is None:
            continue
        text = _message_text(raw)
        if not text:
            continue
        out.append(Message(role=role, text=text, index=len(out)))

    if not out:
        raise ParseError("Claude conversation contains no supported user/assistant text")
    return out


def load(source: str, text: str) -> Conversation:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError("invalid Claude JSON") from exc

    conversation = _select_conversation(value)
    messages = extract_messages(conversation)

    title = ""
    for key in ("name", "title"):
        candidate = conversation.get(key)
        if isinstance(candidate, str):
            title = candidate.strip()
            if title:
                break

    raw_messages = conversation.get("chat_messages", [])
    return Conversation(
        title=title,
        messages=messages,
        source=SourceInfo(
            kind="claude_json",
            locator=str(Path(source)),
            fingerprint=source_fingerprint(text),
            metadata={
                "format": "claude_conversation_json",
                "runtime_marker_counts": inspect_raw_text(text),
            },
        ),
        snapshot=SnapshotInfo(
            created_at=_timestamp(conversation.get("created_at")),
            updated_at=_timestamp(conversation.get("updated_at")),
            raw_node_count=len(raw_messages) if isinstance(raw_messages, list) else None,
        ),
    )
