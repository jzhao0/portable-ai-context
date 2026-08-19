from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
import zipfile


DEFAULT_USER_SENTINEL = "PAIC_GROK_EXPORT_SENTINEL_20260819_USER"
DEFAULT_ASSISTANT_SENTINEL = "PAIC_GROK_EXPORT_SENTINEL_20260819_ASSISTANT"
SAFE_LITERAL_VALUES = {
    "user",
    "assistant",
    "human",
    "system",
    "text",
    "message",
    "messages",
    "content",
    "Grok",
}
SUSPICIOUS_KEY_PATTERNS = (
    re.compile(r"@"),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"^\d{4}-\d{2}-\d{2}(?:[T _].*)?$"),
    re.compile(r"^\d{8,}$"),
    re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.IGNORECASE),
    re.compile(r"^[0-9a-f]{24,}$", re.IGNORECASE),
    re.compile(r"^[A-Za-z0-9_-]{40,}$"),
)


class ProbeError(RuntimeError):
    pass


def _safe_key(key: Any) -> str:
    if not isinstance(key, str):
        return "<redacted-key>"
    if len(key) > 120 or any(pattern.search(key) for pattern in SUSPICIOUS_KEY_PATTERNS):
        return "<redacted-key>"
    return key


def _marker_occurrences(value: Any, marker: str) -> int:
    if isinstance(value, str):
        return value.count(marker)
    if isinstance(value, list):
        return sum(_marker_occurrences(item, marker) for item in value)
    if isinstance(value, dict):
        return sum(
            _marker_occurrences(key, marker) + _marker_occurrences(item, marker)
            for key, item in value.items()
        )
    return 0


def _contains_marker(value: Any, marker: str) -> bool:
    return _marker_occurrences(value, marker) > 0


def _minimal_common_containers(
    value: Any,
    user_sentinel: str,
    assistant_sentinel: str,
) -> list[Any]:
    """Return deepest dict/list containers whose subtree contains both markers."""
    if not isinstance(value, (dict, list)):
        return []

    children = value.values() if isinstance(value, dict) else value
    child_candidates: list[Any] = []
    for child in children:
        child_candidates.extend(
            _minimal_common_containers(child, user_sentinel, assistant_sentinel)
        )

    has_user = _contains_marker(value, user_sentinel)
    has_assistant = _contains_marker(value, assistant_sentinel)
    if not (has_user and has_assistant):
        return []
    if child_candidates:
        return child_candidates
    return [value]


def _parent_container(root: Any, target: Any) -> Any | None:
    """Find the direct list/dict parent of ``target`` by object identity."""
    if not isinstance(root, (dict, list)):
        return None
    children = root.values() if isinstance(root, dict) else root
    for child in children:
        if child is target:
            return root
        parent = _parent_container(child, target)
        if parent is not None:
            return parent
    return None


def _discovery_contexts(
    document: Any,
    user_sentinel: str,
    assistant_sentinel: str,
) -> list[Any]:
    """Keep the minimal common container plus one object field label for arrays.

    A minimal list such as a turn array has useful ordering but no field name.
    If that list is directly stored under a JSON object key, retain exactly that
    parent object so the sanitized specimen preserves the field label. Dict
    candidates already expose their own field names and are not expanded.
    """
    contexts: list[Any] = []
    seen: set[int] = set()
    for candidate in _minimal_common_containers(
        document, user_sentinel, assistant_sentinel
    ):
        context = candidate
        if isinstance(candidate, list):
            parent = _parent_container(document, candidate)
            if isinstance(parent, dict):
                context = parent
        identity = id(context)
        if identity not in seen:
            seen.add(identity)
            contexts.append(context)
    return contexts


def _sanitize_string(value: str, user_sentinel: str, assistant_sentinel: str) -> str:
    has_user = user_sentinel in value
    has_assistant = assistant_sentinel in value
    if has_user and has_assistant:
        return user_sentinel + " | " + assistant_sentinel
    if has_user:
        return user_sentinel
    if has_assistant:
        return assistant_sentinel
    if value in SAFE_LITERAL_VALUES:
        return value
    return "<redacted:string>"


def _sanitize(value: Any, user_sentinel: str, assistant_sentinel: str) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        duplicate_redacted_keys = 0
        for key, item in value.items():
            safe_key = _safe_key(key)
            if safe_key in sanitized:
                duplicate_redacted_keys += 1
                safe_key = f"<redacted-key-{duplicate_redacted_keys}>"
            sanitized[safe_key] = _sanitize(item, user_sentinel, assistant_sentinel)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item, user_sentinel, assistant_sentinel) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value, user_sentinel, assistant_sentinel)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return "<redacted:number>"
    return f"<redacted:{type(value).__name__}>"


def _node_count(value: Any, *, stop_after: int) -> int:
    count = 0
    stack = [value]
    while stack:
        node = stack.pop()
        count += 1
        if count > stop_after:
            return count
        if isinstance(node, dict):
            for key, item in node.items():
                count += 1  # count the structural key separately
                if count > stop_after:
                    return count
                stack.append(item)
        elif isinstance(node, list):
            stack.extend(node)
    return count


def _decode_json(raw: bytes) -> Any | None:
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def _decode_jsonl(raw: bytes, *, max_line_bytes: int) -> list[Any]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return []
    records: list[Any] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        if len(line.encode("utf-8")) > max_line_bytes:
            raise ProbeError("refusing JSONL record larger than configured document limit")
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def _load_one_file(path: Path, max_bytes: int) -> tuple[list[Any], int, int, int]:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return [], 0, 1, 0
    if suffix not in {".json", ".jsonl", ".ndjson"}:
        return [], 0, 0, 1
    if path.stat().st_size > max_bytes:
        raise ProbeError("refusing provider document larger than configured size limit")
    raw = path.read_bytes()
    if suffix == ".json":
        value = _decode_json(raw)
        return ([value] if value is not None else []), 0, 0, 0
    records = _decode_jsonl(raw, max_line_bytes=max_bytes)
    return records, len(records), 0, 0


def _load_zip(path: Path, max_bytes: int) -> tuple[list[Any], int, int, int]:
    documents: list[Any] = []
    jsonl_records = 0
    html_count = 0
    other_count = 0
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix in {".html", ".htm"}:
                html_count += 1
                continue
            if suffix not in {".json", ".jsonl", ".ndjson"}:
                other_count += 1
                continue
            if info.file_size > max_bytes:
                raise ProbeError("refusing provider document larger than configured size limit")
            with archive.open(info) as handle:
                raw = handle.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ProbeError("provider document exceeded configured size limit")
            if suffix == ".json":
                value = _decode_json(raw)
                if value is not None:
                    documents.append(value)
            else:
                records = _decode_jsonl(raw, max_line_bytes=max_bytes)
                documents.extend(records)
                jsonl_records += len(records)
    return documents, jsonl_records, html_count, other_count


def load_documents(source: Path, max_bytes: int) -> tuple[list[Any], int, int, int]:
    if source.is_file() and zipfile.is_zipfile(source):
        return _load_zip(source, max_bytes)
    if source.is_file():
        return _load_one_file(source, max_bytes)
    if source.is_dir():
        documents: list[Any] = []
        jsonl_records = 0
        html_count = 0
        other_count = 0
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            docs, line_records, html_seen, other_seen = _load_one_file(path, max_bytes)
            documents.extend(docs)
            jsonl_records += line_records
            html_count += html_seen
            other_count += other_seen
        return documents, jsonl_records, html_count, other_count
    raise ProbeError("source path does not exist")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_probe(
    *,
    source: Path,
    user_sentinel: str,
    assistant_sentinel: str,
    output: Path,
    max_document_mb: int,
    max_specimen_nodes: int,
) -> dict[str, Any]:
    if not user_sentinel or len(user_sentinel) < 16:
        raise ProbeError("user sentinel must be at least 16 characters and deliberately non-sensitive")
    if not assistant_sentinel or len(assistant_sentinel) < 16:
        raise ProbeError("assistant sentinel must be at least 16 characters and deliberately non-sensitive")
    if user_sentinel == assistant_sentinel or user_sentinel in assistant_sentinel or assistant_sentinel in user_sentinel:
        raise ProbeError("user and assistant sentinels must be distinct and non-overlapping")
    if max_document_mb <= 0 or max_specimen_nodes <= 0:
        raise ProbeError("probe limits must be positive")

    documents, jsonl_records, html_count, other_count = load_documents(
        source, max_document_mb * 1024 * 1024
    )
    if not documents:
        raise ProbeError(
            "no readable JSON/JSONL documents found "
            f"(HTML documents seen: {html_count}; other files seen: {other_count})"
        )

    user_occurrences = sum(_marker_occurrences(doc, user_sentinel) for doc in documents)
    assistant_occurrences = sum(
        _marker_occurrences(doc, assistant_sentinel) for doc in documents
    )
    if user_occurrences != 1 or assistant_occurrences != 1:
        raise ProbeError(
            "expected each Grok sentinel exactly once; "
            f"user occurrences: {user_occurrences}; assistant occurrences: {assistant_occurrences}"
        )

    contexts: list[Any] = []
    for document in documents:
        contexts.extend(_discovery_contexts(document, user_sentinel, assistant_sentinel))
    if len(contexts) != 1:
        raise ProbeError(
            "expected exactly one minimal JSON context containing both Grok sentinels; "
            f"found {len(contexts)}"
        )

    context = contexts[0]
    nodes = _node_count(context, stop_after=max_specimen_nodes)
    if nodes > max_specimen_nodes:
        raise ProbeError(
            "minimal Grok sentinel context exceeds the structural node limit; "
            "do not manually trim the raw export"
        )

    specimen = _sanitize(context, user_sentinel, assistant_sentinel)
    encoded = (json.dumps(specimen, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if user_sentinel.encode("utf-8") not in encoded or assistant_sentinel.encode("utf-8") not in encoded:
        raise ProbeError("sanitized specimen unexpectedly lost a Grok sentinel")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)

    return {
        "ok": True,
        "provider": "grok",
        "probe_mode": "unknown_schema_minimal_common_context_v1",
        "json_documents_scanned": len(documents),
        "jsonl_records_scanned": jsonl_records,
        "html_documents_seen": html_count,
        "other_files_seen": other_count,
        "user_sentinel_occurrences": user_occurrences,
        "assistant_sentinel_occurrences": assistant_occurrences,
        "minimal_context_type": "object" if isinstance(context, dict) else "array",
        "minimal_context_nodes": nodes,
        "sanitized_specimen_sha256": _sha256_bytes(encoded),
        "sanitized_specimen_bytes": len(encoded),
        "output_file": output.name,
        "schema_claimed": False,
        "raw_export_not_copied": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover a sanitized JSON structure around one deliberately non-sensitive "
            "Grok sentinel conversation without assuming an xAI export schema."
        )
    )
    parser.add_argument("source", help="local xAI account-download ZIP, JSON/JSONL file, or extracted directory")
    parser.add_argument("--user-sentinel", default=DEFAULT_USER_SENTINEL)
    parser.add_argument("--assistant-sentinel", default=DEFAULT_ASSISTANT_SENTINEL)
    parser.add_argument(
        "-o",
        "--output",
        default="paic-grok-export-shape.sanitized.json",
        help="sanitized structural specimen to create",
    )
    parser.add_argument("--max-document-mb", type=int, default=256)
    parser.add_argument("--max-specimen-nodes", type=int, default=5000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_probe(
            source=Path(args.source),
            user_sentinel=args.user_sentinel,
            assistant_sentinel=args.assistant_sentinel,
            output=Path(args.output),
            max_document_mb=args.max_document_mb,
            max_specimen_nodes=args.max_specimen_nodes,
        )
    except ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"error: local xAI export read failed: {type(exc).__name__}", file=sys.stderr)
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
