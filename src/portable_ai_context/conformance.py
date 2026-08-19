from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

from .adapters import clean_html as clean_html_adapter
from .adapters import compact_txt as compact_txt_adapter
from .adapters import jsonl as jsonl_adapter
from .exporters import clean_html as export_clean_html
from .exporters import compact_txt as export_compact_txt
from .exporters import jsonl as export_jsonl
from .integrity import inspect as inspect_integrity
from .models import Conversation
from .utils import normalize_text


CANONICAL_ROLES = frozenset({"user", "assistant"})


@dataclass(slots=True, frozen=True)
class ConformanceViolation:
    code: str
    message: str


@dataclass(slots=True)
class ConformanceReport:
    ok: bool
    source_kind: str
    message_count: int
    conversation_digest: str
    checks: dict[str, bool]
    violations: list[ConformanceViolation]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "source_kind": self.source_kind,
            "message_count": self.message_count,
            "conversation_digest": self.conversation_digest,
            "checks": dict(self.checks),
            "violations": [asdict(item) for item in self.violations],
        }


def _canonical_private_surface(conversation: Conversation) -> Any:
    """Return canonical content/metadata fields that must not carry runtime values.

    Source locator and fingerprint are intentionally excluded: a local source path is
    provenance, not normalized conversation content, and fingerprints are derived data.
    """
    return {
        "title": conversation.title,
        "messages": [
            {
                "role": message.role,
                "text": message.text,
                "metadata": message.metadata,
            }
            for message in conversation.messages
        ],
        "conversation_metadata": conversation.metadata,
        "source_metadata": conversation.source.metadata,
        "snapshot_metadata": conversation.snapshot.metadata,
    }


def _contains_value(value: Any, needle: str) -> bool:
    if isinstance(value, str):
        return needle in value
    if isinstance(value, dict):
        return any(
            _contains_value(key, needle) or _contains_value(item, needle)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple, set)):
        return any(_contains_value(item, needle) for item in value)
    return False


def _roundtrip_digest(conversation: Conversation, format_name: str) -> str:
    if format_name == "clean_html":
        text = export_clean_html(conversation)
        loaded = clean_html_adapter.load("conformance.clean.html", text)
    elif format_name == "compact_txt":
        text = export_compact_txt(conversation)
        loaded = compact_txt_adapter.load("conformance.compact.txt", text)
    elif format_name == "jsonl":
        text = export_jsonl(conversation)
        loaded = jsonl_adapter.load("conformance.clean.jsonl", text)
    else:  # pragma: no cover - internal programming error guard
        raise ValueError(format_name)
    return inspect_integrity(loaded).conversation_digest


def inspect_conformance(
    conversation: Conversation,
    *,
    expected_messages: Sequence[tuple[str, str]] | None = None,
    forbidden_values: Iterable[str] = (),
) -> ConformanceReport:
    """Evaluate the shared alpha canonical/adapter contract.

    The returned report is content-free: it contains counts, hashes, check names,
    and predefined violation messages, never message text or forbidden values.
    """
    checks: dict[str, bool] = {}
    violations: list[ConformanceViolation] = []

    def record(name: str, passed: bool, code: str, message: str) -> None:
        checks[name] = bool(passed)
        if not passed:
            violations.append(ConformanceViolation(code=code, message=message))

    messages = conversation.messages
    integrity = inspect_integrity(conversation)

    record(
        "message_stream_nonempty",
        bool(messages),
        "empty_message_stream",
        "canonical conversation contains no messages",
    )
    record(
        "source_kind_present",
        isinstance(conversation.source.kind, str) and bool(conversation.source.kind.strip()),
        "missing_source_kind",
        "canonical source kind is missing",
    )
    record(
        "canonical_roles",
        all(message.role in CANONICAL_ROLES for message in messages),
        "noncanonical_role",
        "canonical message stream contains an unsupported role",
    )
    record(
        "contiguous_indices",
        [message.index for message in messages] == list(range(len(messages))),
        "noncontiguous_indices",
        "canonical message indices are not contiguous from zero",
    )
    record(
        "nonempty_text",
        all(isinstance(message.text, str) and bool(message.text.strip()) for message in messages),
        "empty_message_text",
        "canonical message stream contains empty or non-string text",
    )

    expected_user_count = sum(message.role == "user" for message in messages)
    expected_assistant_count = sum(message.role == "assistant" for message in messages)
    record(
        "integrity_consistent",
        integrity.message_count == len(messages)
        and integrity.user_count == expected_user_count
        and integrity.assistant_count == expected_assistant_count
        and isinstance(integrity.conversation_digest, str)
        and len(integrity.conversation_digest) == 64,
        "integrity_mismatch",
        "integrity report is inconsistent with the canonical message stream",
    )

    if expected_messages is not None:
        actual = [(message.role, normalize_text(message.text)) for message in messages]
        expected = [(role, normalize_text(text)) for role, text in expected_messages]
        record(
            "expected_messages",
            actual == expected,
            "expected_messages_mismatch",
            "canonical role/text sequence does not match the expected synthetic contract",
        )

    forbidden = [value for value in forbidden_values if isinstance(value, str) and value]
    if forbidden:
        surface = _canonical_private_surface(conversation)
        leaked = any(_contains_value(surface, value) for value in forbidden)
        record(
            "forbidden_values_absent",
            not leaked,
            "forbidden_value_present",
            "a forbidden runtime/private value entered canonical content or metadata",
        )

    for format_name in ("clean_html", "compact_txt", "jsonl"):
        check_name = f"roundtrip_{format_name}"
        try:
            roundtrip_digest = _roundtrip_digest(conversation, format_name)
            passed = roundtrip_digest == integrity.conversation_digest
        except Exception:  # report must stay content-free even when a parser fails
            passed = False
        record(
            check_name,
            passed,
            f"{check_name}_mismatch",
            f"{format_name} round trip did not preserve the canonical conversation digest",
        )

    return ConformanceReport(
        ok=not violations,
        source_kind=conversation.source.kind if isinstance(conversation.source.kind, str) else "",
        message_count=len(messages),
        conversation_digest=integrity.conversation_digest,
        checks=checks,
        violations=violations,
    )
