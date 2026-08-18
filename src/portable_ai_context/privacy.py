from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Pattern

from .models import Conversation


RUNTIME_MARKERS = {
    "client_bootstrap": re.compile(r"client-bootstrap", re.I),
    "access_token_field": re.compile(r"accessToken", re.I),
    "session_token_field": re.compile(r"sessionToken", re.I),
    "authorization_field": re.compile(r"authorization", re.I),
    "statsig_field": re.compile(r"statsig", re.I),
}

# Counts only. Matched values are never returned.
BODY_PATTERNS: dict[str, Pattern[str]] = {
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    "github_token": re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}", re.I),
    "private_key_header": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


@dataclass(slots=True)
class PrivacyReport:
    runtime_marker_counts: dict[str, int]
    body_secret_counts: dict[str, int]
    safe_to_share_automatically: bool

    def to_dict(self):
        return asdict(self)


def inspect_raw_text(text: str) -> dict[str, int]:
    return {name: len(pattern.findall(text)) for name, pattern in RUNTIME_MARKERS.items()}


def inspect_conversation(conversation: Conversation) -> PrivacyReport:
    body = "\n".join(m.text for m in conversation.messages)
    counts = {name: len(pattern.findall(body)) for name, pattern in BODY_PATTERNS.items()}
    # Runtime markers can legitimately be discussed in a conversation, so canonical
    # text occurrence is not proof of leakage. Only body-secret patterns make the
    # automatic-share flag false.
    runtime_counts = conversation.source.metadata.get("runtime_marker_counts", {})
    if not isinstance(runtime_counts, dict):
        runtime_counts = {}
    return PrivacyReport(
        runtime_marker_counts={str(k): int(v) for k, v in runtime_counts.items() if isinstance(v, int)},
        body_secret_counts=counts,
        safe_to_share_automatically=not any(counts.values()),
    )
