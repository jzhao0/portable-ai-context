from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile
from typing import Any, Iterable, Iterator


USER_MARKER_DEFAULT = "PAIC_GROK_EXPORT_SENTINEL_20260819_USER"
ASSISTANT_MARKER_DEFAULT = "PAIC_GROK_EXPORT_SENTINEL_20260819_ASSISTANT"

SAFE_STRUCTURAL_LITERALS = frozenset(
    {
        "assistant",
        "human",
        "model",
        "system",
        "text",
        "user",
    }
)

SUSPICIOUS_KEY_PATTERNS = (
    re.compile(r"@"),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"^[0-9]{8,}$"),
    re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.IGNORECASE),
    re.compile(r"^[0-9a-f]{24,}$", re.IGNORECASE),
    re.compile(r"^[A-Za-z0-9+/=_-]{40,}$"),
)

JSON_SUFFIXES = frozenset({".json"})
JSONL_SUFFIXES = frozenset({".jsonl", ".ndjson"})
HTML_SUFFIXES = frozenset({".html", ".htm"})


class ProbeError(RuntimeError):
    pass


class _Budget:
    def __init__(self, *, max_nodes: int, max_depth: int) -> None:
        self.max_nodes = max_nodes
        self.max_depth = max_depth
        self.nodes_seen = 0

    def visit(self, depth: int) -> None:
        if depth > self.max_depth:
            raise ProbeError("JSON nesting exceeded the configured depth limit")
        self.nodes_seen += 1
        if self.nodes_seen > self.max_nodes:
            raise ProbeError("JSON structure exceeded the configured node limit")


def _marker_mask_for_string(value: str, user_marker: str, assistant_marker: str) -> int:
    mask = 0
    if user_marker in value:
        mask |= 1
    if assistant_marker in value:
        mask |= 2
    return mask


def _find_minimal_dict_contexts(
    value: Any,
    *,
    user_marker: str,
    assistant_marker: str,
    budget: _Budget,
    depth: int = 0,
) -> tuple[int, list[dict[str, Any]]]:
    """Return marker mask and minimal dict nodes whose subtrees contain both markers.

    No provider field names participate in discovery. A parent dictionary is
    selected only when its subtree contains both fixed markers and no nested
    dictionary already contains both markers.
    """

    budget.visit(depth)

    if isinstance(value, str):
        return _marker_mask_for_string(value, user_marker, assistant_marker), []

    if isinstance(value, dict):
        mask = 0
        nested: list[dict[str, Any]] = []
        for key, child in value.items():
            if isinstance(key, str):
                mask |= _marker_mask_for_string(key, user_marker, assistant_marker)
            child_mask, child_contexts = _find_minimal_dict_contexts(
                child,
                user_marker=user_marker,
                assistant_marker=assistant_marker,
                budget=budget,
                depth=depth + 1,
            )
            mask |= child_mask
            nested.extend(child_contexts)

        if mask == 3:
            if nested:
                return mask, nested
            return mask, [value]
        return mask, nested

    if isinstance(value, list):
        mask = 0
        nested: list[dict[str, Any]] = []
        for child in value:
            child_mask, child_contexts = _find_minimal_dict_contexts(
                child,
                user_marker=user_marker,
                assistant_marker=assistant_marker,
                budget=budget,
                depth=depth + 1,
            )
            mask |= child_mask
            nested.extend(child_contexts)
        return mask, nested

    return 0, []


def _marker_occurrences(value: Any, marker: str, *, max_nodes: int, max_depth: int) -> int:
    budget = _Budget(max_nodes=max_nodes, max_depth=max_depth)
    count = 0

    def walk(node: Any, depth: int) -> None:
        nonlocal count
        budget.visit(depth)
        if isinstance(node, str):
            count += node.count(marker)
        elif isinstance(node, dict):
            for key, child in node.items():
                if isinstance(key, str):
                    count += key.count(marker)
                walk(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                walk(child, depth + 1)

    walk(value, 0)
    return count


def _safe_key(key: Any, redacted_index: int) -> str:
    if not isinstance(key, str):
        return f"<redacted-key-{redacted_index}>"
    if (
        not key
        or len(key) > 120
        or any(ord(char) < 32 for char in key)
        or any(pattern.search(key) for pattern in SUSPICIOUS_KEY_PATTERNS)
    ):
        return f"<redacted-key-{redacted_index}>"
    return key


def _sanitize_string(value: str, user_marker: str, assistant_marker: str) -> str:
    markers: list[str] = []
    if user_marker in value:
        markers.append(user_marker)
    if assistant_marker in value:
        markers.append(assistant_marker)
    if markers:
        return " ".join(markers)
    if value in SAFE_STRUCTURAL_LITERALS:
        return value
    return "<redacted:string>"


def sanitize_unknown_structure(
    value: Any,
    *,
    user_marker: str,
    assistant_marker: str,
    max_nodes: int,
    max_depth: int,
) -> Any:
    budget = _Budget(max_nodes=max_nodes, max_depth=max_depth)

    def sanitize(node: Any, depth: int) -> Any:
        budget.visit(depth)
        if isinstance(node, dict):
            result: dict[str, Any] = {}
            redacted_index = 0
            for key, child in node.items():
                safe_key = _safe_key(key, redacted_index + 1)
                if safe_key.startswith("<redacted-key-"):
                    redacted_index += 1
                while safe_key in result:
                    redacted_index += 1
                    safe_key = f"<redacted-key-{redacted_index}>"
                result[safe_key] = sanitize(child, depth + 1)
            return result
        if isinstance(node, list):
            return [sanitize(child, depth + 1) for child in node]
        if isinstance(node, str):
            return _sanitize_string(node, user_marker, assistant_marker)
        if node is None or isinstance(node, bool):
            return node
        if isinstance(node, (int, float)):
            return "<redacted:number>"
        return f"<redacted:{type(node).__name__}>"

    return sanitize(value, 0)


def _decode_json(raw: bytes) -> Any | None:
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        return None


def _iter_jsonl(raw: bytes, *, max_documents: int) -> Iterator[Any]:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return
    produced = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except (json.JSONDecodeError, RecursionError):
            continue
        produced += 1
        if produced > max_documents:
            raise ProbeError("JSONL/NDJSON record count exceeded the configured document limit")
        yield value


def _bounded_read_file(path: Path, *, max_json_bytes: int) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ProbeError("local export file metadata could not be read") from exc
    if size > max_json_bytes:
        raise ProbeError("refusing JSON/JSONL document larger than the configured per-document limit")
    raw = path.read_bytes()
    if len(raw) > max_json_bytes:
        raise ProbeError("JSON/JSONL document exceeded the configured per-document limit")
    return raw


def _iter_source_files(source: Path, *, output: Path) -> Iterator[Path]:
    if source.is_file():
        yield source
        return
    if source.is_dir():
        try:
            output_resolved = output.resolve()
        except OSError:
            output_resolved = output.absolute()
        for path in source.rglob("*"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                if path.resolve() == output_resolved:
                    continue
            except OSError:
                pass
            yield path
        return
    raise ProbeError("source path does not exist")


def _documents_from_raw(raw: bytes, suffix: str, *, max_documents: int) -> Iterator[Any]:
    if suffix in JSON_SUFFIXES:
        document = _decode_json(raw)
        if document is not None:
            yield document
        return
    if suffix in JSONL_SUFFIXES:
        yield from _iter_jsonl(raw, max_documents=max_documents)


def _scan_source(
    *,
    source: Path,
    output: Path,
    max_json_bytes: int,
    max_total_json_bytes: int,
    max_documents: int,
    max_zip_members: int,
) -> tuple[Iterator[Any], dict[str, int]]:
    counters = {
        "json_files_seen": 0,
        "jsonl_files_seen": 0,
        "html_documents_seen": 0,
        "documents_scanned": 0,
        "bytes_read": 0,
    }

    def account_bytes(amount: int) -> None:
        counters["bytes_read"] += amount
        if counters["bytes_read"] > max_total_json_bytes:
            raise ProbeError("JSON/JSONL bytes exceeded the configured total-read limit")

    def account_document() -> None:
        counters["documents_scanned"] += 1
        if counters["documents_scanned"] > max_documents:
            raise ProbeError("parsed JSON document count exceeded the configured limit")

    def iterator() -> Iterator[Any]:
        if source.is_file() and zipfile.is_zipfile(source):
            with zipfile.ZipFile(source) as archive:
                infos = archive.infolist()
                if len(infos) > max_zip_members:
                    raise ProbeError("ZIP member count exceeded the configured limit")
                for info in infos:
                    if info.is_dir():
                        continue
                    suffix = Path(info.filename).suffix.lower()
                    if suffix in HTML_SUFFIXES:
                        counters["html_documents_seen"] += 1
                        continue
                    if suffix not in JSON_SUFFIXES | JSONL_SUFFIXES:
                        continue
                    if info.file_size > max_json_bytes:
                        raise ProbeError(
                            "refusing ZIP JSON/JSONL member larger than the configured per-document limit"
                        )
                    with archive.open(info) as handle:
                        raw = handle.read(max_json_bytes + 1)
                    if len(raw) > max_json_bytes:
                        raise ProbeError("ZIP JSON/JSONL member exceeded the configured per-document limit")
                    account_bytes(len(raw))
                    if suffix in JSON_SUFFIXES:
                        counters["json_files_seen"] += 1
                    else:
                        counters["jsonl_files_seen"] += 1
                    remaining = max_documents - counters["documents_scanned"]
                    if remaining <= 0:
                        raise ProbeError("parsed JSON document count exceeded the configured limit")
                    for document in _documents_from_raw(raw, suffix, max_documents=remaining):
                        account_document()
                        yield document
            return

        for path in _iter_source_files(source, output=output):
            suffix = path.suffix.lower()
            if suffix in HTML_SUFFIXES:
                counters["html_documents_seen"] += 1
                continue
            if suffix not in JSON_SUFFIXES | JSONL_SUFFIXES:
                continue
            raw = _bounded_read_file(path, max_json_bytes=max_json_bytes)
            account_bytes(len(raw))
            if suffix in JSON_SUFFIXES:
                counters["json_files_seen"] += 1
            else:
                counters["jsonl_files_seen"] += 1
            remaining = max_documents - counters["documents_scanned"]
            if remaining <= 0:
                raise ProbeError("parsed JSON document count exceeded the configured limit")
            for document in _documents_from_raw(raw, suffix, max_documents=remaining):
                account_document()
                yield document

    return iterator(), counters


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_probe(
    *,
    source: Path,
    output: Path,
    user_marker: str,
    assistant_marker: str,
    max_json_mb: int,
    max_total_json_mb: int,
    max_documents: int,
    max_zip_members: int,
    max_nodes: int,
    max_depth: int,
    max_specimen_kb: int,
) -> dict[str, Any]:
    if not user_marker or not assistant_marker:
        raise ProbeError("both deliberately non-sensitive sentinel markers are required")
    if user_marker == assistant_marker:
        raise ProbeError("user and assistant sentinel markers must differ")
    if len(user_marker) < 16 or len(assistant_marker) < 16:
        raise ProbeError("sentinel markers must each be at least 16 characters")
    for name, value in {
        "max-json-mb": max_json_mb,
        "max-total-json-mb": max_total_json_mb,
        "max-documents": max_documents,
        "max-zip-members": max_zip_members,
        "max-nodes": max_nodes,
        "max-depth": max_depth,
        "max-specimen-kb": max_specimen_kb,
    }.items():
        if value <= 0:
            raise ProbeError(f"--{name} must be positive")

    documents, counters = _scan_source(
        source=source,
        output=output,
        max_json_bytes=max_json_mb * 1024 * 1024,
        max_total_json_bytes=max_total_json_mb * 1024 * 1024,
        max_documents=max_documents,
        max_zip_members=max_zip_members,
    )

    matches: list[dict[str, Any]] = []
    total_nodes = 0
    for document in documents:
        remaining_nodes = max_nodes - total_nodes
        if remaining_nodes <= 0:
            raise ProbeError("JSON structure exceeded the configured node limit")
        budget = _Budget(max_nodes=remaining_nodes, max_depth=max_depth)
        _, contexts = _find_minimal_dict_contexts(
            document,
            user_marker=user_marker,
            assistant_marker=assistant_marker,
            budget=budget,
        )
        total_nodes += budget.nodes_seen
        matches.extend(contexts)
        if len(matches) > 1:
            raise ProbeError("expected exactly one minimal dictionary context containing both sentinels; found multiple")

    if counters["documents_scanned"] == 0:
        raise ProbeError(
            "no readable JSON/JSONL/NDJSON documents found "
            f"(HTML documents seen: {counters['html_documents_seen']})"
        )
    if len(matches) != 1:
        raise ProbeError("expected exactly one minimal dictionary context containing both sentinels; found none")

    selected = matches[0]
    user_occurrences = _marker_occurrences(
        selected,
        user_marker,
        max_nodes=max_nodes,
        max_depth=max_depth,
    )
    assistant_occurrences = _marker_occurrences(
        selected,
        assistant_marker,
        max_nodes=max_nodes,
        max_depth=max_depth,
    )
    if user_occurrences < 1 or assistant_occurrences < 1:
        raise ProbeError("selected dictionary context unexpectedly lost a sentinel marker")

    specimen = sanitize_unknown_structure(
        selected,
        user_marker=user_marker,
        assistant_marker=assistant_marker,
        max_nodes=max_nodes,
        max_depth=max_depth,
    )
    encoded = (json.dumps(specimen, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if len(encoded) > max_specimen_kb * 1024:
        raise ProbeError("sanitized structural specimen exceeded the configured size limit")
    if user_marker.encode("utf-8") not in encoded or assistant_marker.encode("utf-8") not in encoded:
        raise ProbeError("sanitized structural specimen unexpectedly lost a sentinel marker")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)

    return {
        "ok": True,
        "provider": "grok",
        "json_files_seen": counters["json_files_seen"],
        "jsonl_ndjson_files_seen": counters["jsonl_files_seen"],
        "html_documents_seen": counters["html_documents_seen"],
        "parsed_documents_scanned": counters["documents_scanned"],
        "json_structure_nodes_scanned": total_nodes,
        "matched_minimal_contexts": 1,
        "user_marker_occurrences_in_context": user_occurrences,
        "assistant_marker_occurrences_in_context": assistant_occurrences,
        "sanitized_specimen_sha256": _sha256_bytes(encoded),
        "sanitized_specimen_bytes": len(encoded),
        "output_file": output.name,
        "raw_export_not_copied": True,
        "schema_fields_assumed": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Discover a content-safe structural specimen from an xAI/Grok account data download "
            "without assuming provider field names."
        )
    )
    parser.add_argument("source", help="local xAI export ZIP, JSON/JSONL/NDJSON file, or directory")
    parser.add_argument("-o", "--output", default="paic-grok-export.sanitized.json")
    parser.add_argument("--user-marker", default=USER_MARKER_DEFAULT)
    parser.add_argument("--assistant-marker", default=ASSISTANT_MARKER_DEFAULT)
    parser.add_argument("--max-json-mb", type=int, default=256)
    parser.add_argument("--max-total-json-mb", type=int, default=512)
    parser.add_argument("--max-documents", type=int, default=512)
    parser.add_argument("--max-zip-members", type=int, default=10000)
    parser.add_argument("--max-nodes", type=int, default=500000)
    parser.add_argument("--max-depth", type=int, default=128)
    parser.add_argument("--max-specimen-kb", type=int, default=1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_probe(
            source=Path(args.source),
            output=Path(args.output),
            user_marker=args.user_marker,
            assistant_marker=args.assistant_marker,
            max_json_mb=args.max_json_mb,
            max_total_json_mb=args.max_total_json_mb,
            max_documents=args.max_documents,
            max_zip_members=args.max_zip_members,
            max_nodes=args.max_nodes,
            max_depth=args.max_depth,
            max_specimen_kb=args.max_specimen_kb,
        )
    except ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, zipfile.BadZipFile) as exc:
        print(f"error: local export read failed: {type(exc).__name__}", file=sys.stderr)
        return 2

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
