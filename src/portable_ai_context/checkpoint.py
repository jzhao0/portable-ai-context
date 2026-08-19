from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

from .compiler.budget import CharacterTokenCounter, TokenCounter, resolve_budget
from .conformance import inspect_conformance
from .errors import PortableAIContextError
from .integrity import inspect as inspect_integrity, message_hash
from .models import Conversation
from .privacy import BODY_PATTERNS
from .utils import normalize_text


POLICY_VERSION = "deterministic-extractive-v1"
DEFAULT_PROFILE = "standard"
MIN_BUDGET_TOKENS = 512
MIN_EXCERPT_CHARS = 64
OMISSION_LABEL = "PAIC DETERMINISTIC OMISSION"

_ENGLISH_STATE_RE = re.compile(
    r"\b(?:todo|next|pending|unresolved|blocker|blocked|waiting|remaining|"
    r"error|failed|failure|pass|passed|verified|confirmed|version|commit|sha|"
    r"merge|merged|issue|pull request|constraint|required|requirement|must|never|"
    r"do not|current breakpoint|next action)\b",
    re.IGNORECASE,
)
_CHINESE_STATE_RE = re.compile(
    r"(?:下一步|待办|未完成|阻塞|等待|剩余|报错|错误|失败|通过|验证|确认|"
    r"版本|提交|合并|关闭|问题|必须|不要|不能|隐私|安全|要求|当前|继续)"
)
_PRIVATE_KEY_MATERIAL_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
    r"(?:-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\Z)",
    re.DOTALL,
)
_REASON_ORDER = {
    "latest_user": 0,
    "latest_assistant": 1,
    "first_user": 2,
    "recent_tail": 3,
    "state_marker": 4,
    "recent_fill": 5,
}


@dataclass(slots=True, frozen=True)
class _PreparedMessage:
    index: int
    role: str
    text: str
    source_hash: str
    state_marker_hits: int
    redaction_counts: dict[str, int]


@dataclass(slots=True)
class _SelectedMessage:
    prepared: _PreparedMessage
    text: str
    reasons: tuple[str, ...]
    truncated: bool


@dataclass(slots=True)
class ExtractiveCheckpointReport:
    policy: str
    source_kind: str
    source_message_count: int
    source_conversation_digest: str
    selected_message_count: int
    selected_indices: list[int]
    first_user_included: bool | None
    latest_user_included: bool | None
    latest_assistant_included: bool | None
    truncated_message_count: int
    redaction_counts: dict[str, int]
    tokenizer: str
    tokenizer_exact: bool
    profile: str | None
    budget_tokens: int
    source_token_estimate: int
    output_token_estimate: int
    compression_ratio: float | None
    budget_met: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ExtractiveCheckpointResult:
    markdown: str
    report: ExtractiveCheckpointReport


def _state_marker_hits(text: str) -> int:
    return len(_ENGLISH_STATE_RE.findall(text)) + len(_CHINESE_STATE_RE.findall(text))


def _redaction_count_template() -> dict[str, int]:
    return {"private_key_material": 0, **{name: 0 for name in BODY_PATTERNS}}


def _redact_text(text: str) -> tuple[str, dict[str, int]]:
    counts = _redaction_count_template()
    redacted, count = _PRIVATE_KEY_MATERIAL_RE.subn("[REDACTED:private_key_material]", text)
    counts["private_key_material"] = count
    for name, pattern in BODY_PATTERNS.items():
        redacted, count = pattern.subn(f"[REDACTED:{name}]", redacted)
        counts[name] = count
    return normalize_text(redacted), counts


def _prepare_messages(conversation: Conversation) -> list[_PreparedMessage]:
    prepared: list[_PreparedMessage] = []
    for message in conversation.messages:
        safe_text, redaction_counts = _redact_text(message.text)
        prepared.append(
            _PreparedMessage(
                index=message.index,
                role=message.role,
                text=safe_text,
                source_hash=message_hash(message.role, message.text),
                state_marker_hits=_state_marker_hits(safe_text),
                redaction_counts=redaction_counts,
            )
        )
    return prepared


def _first_index(messages: list[_PreparedMessage], role: str) -> int | None:
    return next((message.index for message in messages if message.role == role), None)


def _last_index(messages: list[_PreparedMessage], role: str) -> int | None:
    return next((message.index for message in reversed(messages) if message.role == role), None)


def _sort_reasons(reasons: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons), key=lambda value: (_REASON_ORDER.get(value, 99), value)))


def _excerpt_text(text: str, keep_chars: int) -> tuple[str, bool]:
    if keep_chars >= len(text):
        return text, False
    keep_chars = max(1, keep_chars)
    head_chars = max(1, int(keep_chars * 0.7))
    tail_chars = max(0, keep_chars - head_chars)
    omitted = max(0, len(text) - head_chars - tail_chars)
    marker = f"\n[{OMISSION_LABEL}: {omitted} CHARACTERS OMITTED]\n"
    tail = text[-tail_chars:] if tail_chars else ""
    return text[:head_chars] + marker + tail, True


def _render_block(selected: _SelectedMessage) -> str:
    prepared = selected.prepared
    reasons = ", ".join(selected.reasons)
    return (
        f"### SOURCE MESSAGE {prepared.index + 1} [{prepared.role.upper()}]\n"
        f"- source_index: {prepared.index}\n"
        f"- source_message_sha256: {prepared.source_hash}\n"
        f"- selection_reason: {reasons}\n"
        f"- state_marker_hits: {prepared.state_marker_hits}\n\n"
        f"{selected.text}\n"
    )


def _render_prefix(
    *,
    source_kind: str,
    source_message_count: int,
    source_digest: str,
) -> str:
    return (
        "# PAIC Deterministic Extractive Checkpoint\n\n"
        "> This artifact is deterministic extractive evidence, not an AI summary. "
        "Do not infer missing decisions, status, or intent beyond the quoted source excerpts.\n\n"
        "## Source integrity\n\n"
        f"- policy: `{POLICY_VERSION}`\n"
        f"- source_kind: `{source_kind}`\n"
        f"- source_message_count: `{source_message_count}`\n"
        f"- source_conversation_digest: `{source_digest}`\n"
        "- derived_secret_redaction: `supported patterns applied before selected excerpts are rendered`\n\n"
        "## Selection policy\n\n"
        "Priority is deterministic: latest user/assistant evidence, first-user goal anchor, "
        "recent tail, older explicit state-marker messages, then recent fill if budget remains. "
        "Selection does not classify statements as true/current/completed.\n\n"
        "Messages may be excerpted only when necessary to satisfy the configured budget; "
        f"every such cut is marked with `{OMISSION_LABEL}` and an omitted-character count.\n\n"
        "## Selected chronological evidence\n\n"
    )


def _render_suffix() -> str:
    return (
        "\n## Handoff rule\n\n"
        "Use the selected excerpts as auditable source evidence. Preserve their chronology and hashes. "
        "If a needed fact is absent or conflicts across excerpts, treat it as unknown/unresolved rather than inventing a resolution.\n"
    )


def _render_checkpoint(prefix: str, selected: dict[int, _SelectedMessage], suffix: str) -> str:
    blocks = "\n".join(_render_block(selected[index]) for index in sorted(selected))
    return prefix + blocks + suffix


def _fit_candidate(
    *,
    prepared: _PreparedMessage,
    reasons: Iterable[str],
    selected: dict[int, _SelectedMessage],
    prefix: str,
    suffix: str,
    counter: TokenCounter,
    total_budget: int,
    phase_budget: int,
) -> _SelectedMessage | None:
    normalized_reasons = _sort_reasons(reasons)
    if phase_budget <= 0:
        return None

    def feasible(keep_chars: int) -> tuple[bool, _SelectedMessage]:
        text, truncated = _excerpt_text(prepared.text, keep_chars)
        candidate = _SelectedMessage(
            prepared=prepared,
            text=text,
            reasons=normalized_reasons,
            truncated=truncated,
        )
        block_tokens = counter.count(_render_block(candidate))
        if block_tokens > phase_budget:
            return False, candidate
        provisional = dict(selected)
        provisional[prepared.index] = candidate
        total_tokens = counter.count(_render_checkpoint(prefix, provisional, suffix))
        return total_tokens <= total_budget, candidate

    full_ok, full_candidate = feasible(len(prepared.text))
    if full_ok:
        return full_candidate

    if len(prepared.text) <= MIN_EXCERPT_CHARS:
        return None

    low = MIN_EXCERPT_CHARS
    high = len(prepared.text) - 1
    best: _SelectedMessage | None = None
    while low <= high:
        middle = (low + high) // 2
        ok, candidate = feasible(middle)
        if ok:
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


def _phase_token_limit(total_available: int, fraction: float, floor: int = 64) -> int:
    return max(floor, int(total_available * fraction))


def _selected_redaction_counts(selected: dict[int, _SelectedMessage]) -> dict[str, int]:
    totals = _redaction_count_template()
    for item in selected.values():
        for name, count in item.prepared.redaction_counts.items():
            totals[name] += count
    return totals


def build_extractive_checkpoint(
    conversation: Conversation,
    *,
    budget_tokens: int | None = None,
    profile: str | None = None,
    token_counter: TokenCounter | None = None,
    chars_per_token: float = 4.0,
) -> ExtractiveCheckpointResult:
    """Build a deterministic, secret-redacted, no-AI extractive checkpoint."""
    conformance = inspect_conformance(conversation)
    if not conformance.ok:
        raise PortableAIContextError(
            "conversation failed canonical conformance; run 'paic conform' for content-free details"
        )

    if budget_tokens is None and profile is None:
        profile = DEFAULT_PROFILE
    resolved_budget, resolved_profile = resolve_budget(
        budget_tokens=budget_tokens,
        profile=profile,
    )
    if resolved_budget is None:  # defensive; default above guarantees a budget
        raise AssertionError("extractive checkpoint requires a resolved budget")
    if resolved_budget < MIN_BUDGET_TOKENS:
        raise ValueError(f"extractive checkpoint budget must be at least {MIN_BUDGET_TOKENS} tokens")

    counter = token_counter or CharacterTokenCounter(chars_per_token=chars_per_token)
    integrity = inspect_integrity(conversation)
    prepared = _prepare_messages(conversation)
    source_kind = conformance.source_kind

    prefix = _render_prefix(
        source_kind=source_kind,
        source_message_count=len(prepared),
        source_digest=integrity.conversation_digest,
    )
    suffix = _render_suffix()
    empty_tokens = counter.count(prefix + suffix)
    if empty_tokens >= resolved_budget:
        raise ValueError("extractive checkpoint budget is too small for the fixed checkpoint envelope")
    available = resolved_budget - empty_tokens

    by_index = {message.index: message for message in prepared}
    first_user = _first_index(prepared, "user")
    latest_user = _last_index(prepared, "user")
    latest_assistant = _last_index(prepared, "assistant")

    pin_reasons: dict[int, set[str]] = {}
    for index, reason in (
        (latest_user, "latest_user"),
        (latest_assistant, "latest_assistant"),
        (first_user, "first_user"),
    ):
        if index is not None:
            pin_reasons.setdefault(index, set()).add(reason)

    selected: dict[int, _SelectedMessage] = {}
    pin_total = _phase_token_limit(available, 0.50)
    per_pin = max(64, pin_total // max(1, len(pin_reasons)))
    pin_order: list[int] = []
    for index in (latest_user, latest_assistant, first_user):
        if index is not None and index not in pin_order:
            pin_order.append(index)
    for index in pin_order:
        candidate = _fit_candidate(
            prepared=by_index[index],
            reasons=pin_reasons[index],
            selected=selected,
            prefix=prefix,
            suffix=suffix,
            counter=counter,
            total_budget=resolved_budget,
            phase_budget=per_pin,
        )
        if candidate is not None:
            selected[index] = candidate

    tail_budget = _phase_token_limit(available, 0.30)
    tail_used = 0
    for prepared_message in reversed(prepared):
        if prepared_message.index in selected:
            continue
        phase_remaining = tail_budget - tail_used
        if phase_remaining <= 0:
            break
        candidate = _fit_candidate(
            prepared=prepared_message,
            reasons=("recent_tail",),
            selected=selected,
            prefix=prefix,
            suffix=suffix,
            counter=counter,
            total_budget=resolved_budget,
            phase_budget=phase_remaining,
        )
        if candidate is None:
            continue
        selected[prepared_message.index] = candidate
        tail_used += counter.count(_render_block(candidate))

    state_budget = _phase_token_limit(available, 0.20)
    state_used = 0
    state_candidates = sorted(
        (
            message
            for message in prepared
            if message.index not in selected and message.state_marker_hits > 0
        ),
        key=lambda message: (-message.state_marker_hits, -message.index),
    )
    for prepared_message in state_candidates:
        phase_remaining = state_budget - state_used
        if phase_remaining <= 0:
            break
        candidate = _fit_candidate(
            prepared=prepared_message,
            reasons=("state_marker",),
            selected=selected,
            prefix=prefix,
            suffix=suffix,
            counter=counter,
            total_budget=resolved_budget,
            phase_budget=phase_remaining,
        )
        if candidate is None:
            continue
        selected[prepared_message.index] = candidate
        state_used += counter.count(_render_block(candidate))

    # Reuse any quota left by short pinned/tail/state messages for additional recent evidence.
    for prepared_message in reversed(prepared):
        if prepared_message.index in selected:
            continue
        current_tokens = counter.count(_render_checkpoint(prefix, selected, suffix))
        remaining = resolved_budget - current_tokens
        if remaining <= 0:
            break
        candidate = _fit_candidate(
            prepared=prepared_message,
            reasons=("recent_fill",),
            selected=selected,
            prefix=prefix,
            suffix=suffix,
            counter=counter,
            total_budget=resolved_budget,
            phase_budget=remaining,
        )
        if candidate is not None:
            selected[prepared_message.index] = candidate

    markdown = _render_checkpoint(prefix, selected, suffix)
    output_tokens = counter.count(markdown)
    if output_tokens > resolved_budget:
        raise AssertionError("deterministic checkpoint exceeded its validated budget")

    source_text = "\n".join(
        f"[{message.role}]\n{normalize_text(message.text)}" for message in conversation.messages
    )
    source_tokens = counter.count(source_text)
    compression_ratio = (output_tokens / source_tokens) if source_tokens else None
    selected_indices = sorted(selected)
    truncated_count = sum(1 for item in selected.values() if item.truncated)
    redaction_counts = _selected_redaction_counts(selected)

    report = ExtractiveCheckpointReport(
        policy=POLICY_VERSION,
        source_kind=source_kind,
        source_message_count=len(prepared),
        source_conversation_digest=integrity.conversation_digest,
        selected_message_count=len(selected_indices),
        selected_indices=selected_indices,
        first_user_included=(first_user in selected) if first_user is not None else None,
        latest_user_included=(latest_user in selected) if latest_user is not None else None,
        latest_assistant_included=(latest_assistant in selected) if latest_assistant is not None else None,
        truncated_message_count=truncated_count,
        redaction_counts=redaction_counts,
        tokenizer=counter.name,
        tokenizer_exact=counter.exact,
        profile=resolved_profile,
        budget_tokens=resolved_budget,
        source_token_estimate=source_tokens,
        output_token_estimate=output_tokens,
        compression_ratio=compression_ratio,
        budget_met=output_tokens <= resolved_budget,
    )
    return ExtractiveCheckpointResult(markdown=markdown, report=report)
