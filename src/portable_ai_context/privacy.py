from __future__ import annotations

from dataclasses import dataclass, asdict
import re
from typing import Pattern

from .models import Conversation
from .utils import normalize_text


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

PRIVATE_KEY_MATERIAL_PATTERN = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
    r"(?:-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\Z)",
    re.DOTALL,
)
REDACTION_POLICY = "pattern-limited-v1"


@dataclass(slots=True)
class PrivacyReport:
    runtime_marker_counts: dict[str, int]
    body_secret_counts: dict[str, int]
    safe_to_share_automatically: bool

    def to_dict(self):
        return asdict(self)


def redaction_count_template() -> dict[str, int]:
    return {"private_key_material": 0, **{name: 0 for name in BODY_PATTERNS}}


def redact_body_text(text: str) -> tuple[str, dict[str, int]]:
    """Redact currently supported secret-like patterns from one body string.

    The returned counts never contain matched values. This transform is
    deliberately pattern-limited and is not a general DLP/sanitization proof.
    """
    counts = redaction_count_template()
    redacted, count = PRIVATE_KEY_MATERIAL_PATTERN.subn(
        "[REDACTED:private_key_material]", text
    )
    counts["private_key_material"] = count
    for name, pattern in BODY_PATTERNS.items():
        redacted, count = pattern.subn(f"[REDACTED:{name}]", redacted)
        counts[name] = count
    return normalize_text(redacted), counts


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
