from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path

from portable_ai_context.integrity import message_hash
from portable_ai_context.models import Conversation
from .base import CompilerBackend
from .budget import (
    CharacterTokenCounter,
    CompilationReport,
    TokenCounter,
    resolve_budget,
)
from .prompts import BUDGET_SYSTEM, FINAL_SYSTEM, MAP_SYSTEM, MERGE_SYSTEM


def _message_block(index: int, role: str, text: str) -> str:
    return f"\n### MESSAGE {index + 1} [{role.upper()}]\n{text}\n"


def _render_conversation(conversation: Conversation) -> str:
    title = f"# {conversation.title}\n" if conversation.title else ""
    return title + "".join(
        _message_block(message.index, message.role, message.text)
        for message in conversation.messages
    )


def _chunk(conversation: Conversation, max_chars: int) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for message in conversation.messages:
        block = _message_block(message.index, message.role, message.text)
        if buf and size + len(block) > max_chars:
            chunks.append("".join(buf))
            buf, size = [], 0
        buf.append(block)
        size += len(block)
    if buf:
        chunks.append("".join(buf))
    return chunks


def _group(items: list[str], max_chars: int) -> list[list[str]]:
    groups: list[list[str]] = []
    buf: list[str] = []
    size = 0
    for item in items:
        if buf and size + len(item) > max_chars:
            groups.append(buf)
            buf, size = [], 0
        buf.append(item)
        size += len(item)
    if buf:
        groups.append(buf)
    return groups


def _hashes(conversation: Conversation) -> list[str]:
    return [message_hash(m.role, m.text) for m in conversation.messages]


def _load_state(path: Path | None, hashes: list[str]) -> tuple[int, list[str]]:
    if not path or not path.exists():
        return 0, []
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return 0, []
    old = state.get("message_hashes")
    notes = state.get("map_notes")
    if not isinstance(old, list) or not isinstance(notes, list):
        return 0, []
    if len(old) <= len(hashes) and hashes[:len(old)] == old:
        return len(old), [x for x in notes if isinstance(x, str)]
    return 0, []


@dataclass(slots=True)
class CompilationResult:
    final: str
    notes: list[str]
    report: CompilationReport

    def __iter__(self):
        # Preserve the original two-value unpacking API: final, notes = compile_migration(...)
        yield self.final
        yield self.notes


def compile_migration(
    conversation: Conversation,
    *,
    backend: CompilerBackend,
    map_model: str,
    final_model: str,
    chunk_chars: int = 120_000,
    reduce_chars: int = 180_000,
    state_path: str | Path | None = None,
    budget_tokens: int | None = None,
    profile: str | None = None,
    token_counter: TokenCounter | None = None,
    chars_per_token: float = 4.0,
) -> CompilationResult:
    resolved_budget, resolved_profile = resolve_budget(
        budget_tokens=budget_tokens,
        profile=profile,
    )
    counter = token_counter or CharacterTokenCounter(chars_per_token=chars_per_token)
    source_tokens = counter.count(_render_conversation(conversation))

    hashes = _hashes(conversation)
    state = Path(state_path) if state_path else None
    start, notes = _load_state(state, hashes)

    if start < len(conversation.messages):
        partial = Conversation(
            title=conversation.title,
            messages=conversation.messages[start:],
            source=conversation.source,
            snapshot=conversation.snapshot,
            metadata=conversation.metadata,
        )
        chunks = _chunk(partial, chunk_chars)
        for i, chunk in enumerate(chunks, 1):
            notes.append(
                backend.complete(
                    model=map_model,
                    system=MAP_SYSTEM,
                    user=(
                        f"Chunk {i}/{len(chunks)} from an old conversation. Extract continuation-critical state.\n"
                        "----- BEGIN CHUNK -----\n" + chunk + "\n----- END CHUNK -----"
                    ),
                    stage="map",
                )
            )

    if state:
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text(
            json.dumps({"message_hashes": hashes, "map_notes": notes}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    reduced = notes
    while len(reduced) > 1 and len("\n\n".join(reduced)) > reduce_chars:
        next_round: list[str] = []
        for group in _group(reduced, reduce_chars):
            next_round.append(
                backend.complete(
                    model=map_model,
                    system=MERGE_SYSTEM,
                    user="Merge these chronological checkpoint notes:\n\n" + "\n\n".join(group),
                    stage="merge",
                )
            )
        reduced = next_round

    final_input = "\n\n".join(
        f"## CHECKPOINT NOTE {i}\n{note}" for i, note in enumerate(reduced, 1)
    )
    final_user = "Compile the final self-contained migration prompt from these notes:\n\n" + final_input
    if resolved_budget is not None:
        final_user = (
            f"Target final output: no more than {resolved_budget} tokens according to "
            f"the configured {counter.name} counter. Preserve continuation-critical state before background detail.\n\n"
            + final_user
        )

    final = backend.complete(
        model=final_model,
        system=FINAL_SYSTEM,
        user=final_user,
        stage="final",
    )
    output_tokens = counter.count(final)
    budget_reduction_applied = False

    if resolved_budget is not None and output_tokens > resolved_budget:
        budget_reduction_applied = True
        final = backend.complete(
            model=final_model,
            system=BUDGET_SYSTEM,
            user=(
                f"Target: <= {resolved_budget} tokens using the configured {counter.name} counter.\n"
                f"Current count: {output_tokens} tokens.\n"
                "Return only the reduced self-contained migration prompt.\n\n"
                "----- BEGIN CURRENT MIGRATION PROMPT -----\n"
                + final
                + "\n----- END CURRENT MIGRATION PROMPT -----"
            ),
            stage="budget",
        )
        output_tokens = counter.count(final)

    overrun = max(0, output_tokens - resolved_budget) if resolved_budget is not None else 0
    compression_ratio = (output_tokens / source_tokens) if source_tokens else None
    report = CompilationReport(
        tokenizer=counter.name,
        tokenizer_exact=counter.exact,
        profile=resolved_profile,
        budget_tokens=resolved_budget,
        source_token_estimate=source_tokens,
        output_token_estimate=output_tokens,
        compression_ratio=compression_ratio,
        budget_overrun_tokens=overrun,
        budget_met=(overrun == 0) if resolved_budget is not None else None,
        budget_reduction_applied=budget_reduction_applied,
    )
    return CompilationResult(final=final, notes=notes, report=report)
