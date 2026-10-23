from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib

from .models import Conversation
from .utils import normalize_text


@dataclass(slots=True)
class IntegrityReport:
    message_count: int
    user_count: int
    assistant_count: int
    conversation_digest: str
    first_message_hash: str | None
    last_message_hash: str | None
    last_user_hash: str | None
    last_assistant_hash: str | None
    snapshot_updated_at: float | None
    raw_node_count: int | None

    def to_dict(self):
        return asdict(self)


def message_hash(role: str, text: str) -> str:
    raw = f"{role}\0{normalize_text(text)}".encode("utf-8", errors="replace")
    return hashlib.sha256(raw).hexdigest()


def inspect(conversation: Conversation) -> IntegrityReport:
    hashes = [message_hash(m.role, m.text) for m in conversation.messages]
    digest_input = "\n".join(hashes).encode("ascii")
    digest = hashlib.sha256(digest_input).hexdigest()

    last_user = None
    last_assistant = None
    user_count = 0
    assistant_count = 0
    for message, digest_value in zip(conversation.messages, hashes):
        if message.role == "user":
            last_user = digest_value
            user_count += 1
        elif message.role == "assistant":
            last_assistant = digest_value
            assistant_count += 1

    return IntegrityReport(
        message_count=len(conversation.messages),
        user_count=user_count,
        assistant_count=assistant_count,
        conversation_digest=digest,
        first_message_hash=hashes[0] if hashes else None,
        last_message_hash=hashes[-1] if hashes else None,
        last_user_hash=last_user,
        last_assistant_hash=last_assistant,
        snapshot_updated_at=conversation.snapshot.updated_at,
        raw_node_count=conversation.snapshot.raw_node_count,
    )
