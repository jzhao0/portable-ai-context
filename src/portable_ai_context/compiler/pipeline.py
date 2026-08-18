from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from portable_ai_context.integrity import message_hash
from portable_ai_context.models import Conversation
from .base import CompilerBackend
from .prompts import MAP_SYSTEM, MERGE_SYSTEM, FINAL_SYSTEM


def _chunk(conversation: Conversation, max_chars: int) -> list[str]:
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for message in conversation.messages:
        block = f"\n### MESSAGE {message.index + 1} [{message.role.upper()}]\n{message.text}\n"
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


def compile_migration(
    conversation: Conversation,
    *,
    backend: CompilerBackend,
    map_model: str,
    final_model: str,
    chunk_chars: int = 120_000,
    reduce_chars: int = 180_000,
    state_path: str | Path | None = None,
) -> tuple[str, list[str]]:
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
    final = backend.complete(
        model=final_model,
        system=FINAL_SYSTEM,
        user="Compile the final self-contained migration prompt from these notes:\n\n" + final_input,
        stage="final",
    )
    return final, notes
