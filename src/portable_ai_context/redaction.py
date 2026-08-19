from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from .exporters import clean_html, compact_txt, jsonl
from .integrity import inspect as inspect_integrity, message_hash
from .models import Conversation, Message, SourceInfo
from .privacy import REDACTION_POLICY, redact_body_text, redaction_count_template


DERIVED_TITLE = "PAIC Pattern-Limited Redaction Review"


@dataclass(slots=True)
class RedactedMessageEvidence:
    index: int
    role: str
    source_message_sha256: str
    redaction_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class RedactionReviewReport:
    policy: str
    source_kind: str
    source_message_count: int
    source_conversation_digest: str
    redacted_conversation_digest: str
    affected_message_count: int
    total_redaction_counts: dict[str, int]
    affected_messages: list[RedactedMessageEvidence]
    supported_patterns_remaining: int
    manual_review_required: bool
    patterns_are_exhaustive: bool
    original_title_preserved: bool
    source_locator_preserved: bool

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        return value


@dataclass(slots=True)
class RedactionReviewResult:
    conversation: Conversation
    report: RedactionReviewReport


def _add_counts(total: dict[str, int], current: dict[str, int]) -> None:
    for name, count in current.items():
        total[name] = total.get(name, 0) + count


def build_redaction_review(conversation: Conversation) -> RedactionReviewResult:
    """Build a derived, pattern-limited redaction review without mutating input."""
    source_integrity = inspect_integrity(conversation)
    total_counts = redaction_count_template()
    affected: list[RedactedMessageEvidence] = []
    redacted_messages: list[Message] = []

    for message in conversation.messages:
        safe_text, counts = redact_body_text(message.text)
        _add_counts(total_counts, counts)
        if any(counts.values()):
            affected.append(
                RedactedMessageEvidence(
                    index=message.index,
                    role=message.role,
                    source_message_sha256=message_hash(message.role, message.text),
                    redaction_counts=counts,
                )
            )
        redacted_messages.append(
            Message(
                role=message.role,
                text=safe_text,
                index=message.index,
            )
        )

    derived = Conversation(
        title=DERIVED_TITLE,
        messages=redacted_messages,
        source=SourceInfo(
            kind="redacted_review",
            metadata={
                "redaction_policy": REDACTION_POLICY,
                "original_source_kind": conversation.source.kind,
            },
        ),
        metadata={"derived_artifact": True},
    )
    redacted_integrity = inspect_integrity(derived)

    remaining = 0
    for message in derived.messages:
        _, counts = redact_body_text(message.text)
        remaining += sum(counts.values())

    report = RedactionReviewReport(
        policy=REDACTION_POLICY,
        source_kind=conversation.source.kind,
        source_message_count=len(conversation.messages),
        source_conversation_digest=source_integrity.conversation_digest,
        redacted_conversation_digest=redacted_integrity.conversation_digest,
        affected_message_count=len(affected),
        total_redaction_counts=total_counts,
        affected_messages=affected,
        supported_patterns_remaining=remaining,
        manual_review_required=True,
        patterns_are_exhaustive=False,
        original_title_preserved=False,
        source_locator_preserved=False,
    )
    return RedactionReviewResult(conversation=derived, report=report)


def write_redaction_review(
    conversation: Conversation,
    out_dir: str | Path,
) -> dict[str, Path]:
    result = build_redaction_review(conversation)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "redacted_clean_html": out / "conversation.redacted.clean.html",
        "redacted_compact_txt": out / "conversation.redacted.compact.txt",
        "redacted_jsonl": out / "conversation.redacted.jsonl",
        "redaction_report": out / "redaction-report.json",
    }
    paths["redacted_clean_html"].write_text(
        clean_html(result.conversation), encoding="utf-8"
    )
    paths["redacted_compact_txt"].write_text(
        compact_txt(result.conversation), encoding="utf-8"
    )
    paths["redacted_jsonl"].write_text(
        jsonl(result.conversation), encoding="utf-8"
    )
    paths["redaction_report"].write_text(
        json.dumps(
            result.report.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return paths
