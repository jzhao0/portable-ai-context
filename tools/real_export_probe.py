from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile
from typing import Any, Iterable


SAFE_LITERALS = {
    "human",
    "user",
    "assistant",
    "text",
    "Gemini",
    "Gemini Apps",
}
SUSPICIOUS_KEY_PATTERNS = (
    re.compile(r"@"),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27,}$", re.IGNORECASE),
    re.compile(r"^[0-9a-f]{24,}$", re.IGNORECASE),
    re.compile(r"^[A-Za-z0-9_-]{40,}$"),
)
MAX_DEFAULT_JSON_BYTES = 256 * 1024 * 1024


class ProbeError(RuntimeError):
    pass


def _contains_sentinel(value: Any, sentinel: str) -> bool:
    if isinstance(value, str):
        return sentinel in value
    if isinstance(value, list):
        return any(_contains_sentinel(item, sentinel) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_sentinel(key, sentinel) or _contains_sentinel(item, sentinel)
            for key, item in value.items()
        )
    return False


def _is_provider_record(value: dict[str, Any], provider: str) -> bool:
    if provider == "claude":
        return isinstance(value.get("chat_messages"), list)
    if provider == "gemini":
        return "header" in value or "products" in value or "safeHtmlItem" in value
    raise AssertionError(provider)


def _find_records(value: Any, provider: str, sentinel: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if _is_provider_record(node, provider) and _contains_sentinel(node, sentinel):
                matches.append(node)
                return
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(value)
    return matches


def _safe_key(key: Any) -> str:
    if not isinstance(key, str):
        return "<redacted-key>"
    if len(key) > 120 or any(pattern.search(key) for pattern in SUSPICIOUS_KEY_PATTERNS):
        return "<redacted-key>"
    return key


def _sanitize_string(value: str, sentinel: str) -> str:
    if sentinel in value:
        # The sentinel is deliberately public/non-sensitive. Preserve a short string
        # containing it so parser-relevant wrappers such as "Prompted ..." remain visible.
        if len(value) <= 500:
            return value
        position = value.find(sentinel)
        start = max(0, position - 80)
        end = min(len(value), position + len(sentinel) + 80)
        return "<redacted-before>" + value[start:end] + "<redacted-after>"
    if value in SAFE_LITERALS:
        return value
    return f"<redacted:string:length={len(value)}>"


def sanitize(value: Any, sentinel: str) -> Any:
    if isinstance(value, dict):
        return {_safe_key(key): sanitize(item, sentinel) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item, sentinel) for item in value]
    if isinstance(value, str):
        return _sanitize_string(value, sentinel)
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return "<redacted:number>"
    return f"<redacted:{type(value).__name__}>"


def _json_documents_from_zip(path: Path, max_bytes: int) -> tuple[list[Any], int]:
    documents: list[Any] = []
    html_count = 0
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = Path(info.filename).suffix.lower()
            if suffix in {".html", ".htm"}:
                html_count += 1
                continue
            if suffix != ".json":
                continue
            if info.file_size > max_bytes:
                raise ProbeError(
                    f"refusing JSON member larger than {max_bytes} bytes; "
                    "increase --max-json-mb explicitly if this is expected"
                )
            with archive.open(info) as handle:
                raw = handle.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ProbeError("JSON member exceeded configured size limit")
            try:
                documents.append(json.loads(raw.decode("utf-8-sig")))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
    return documents, html_count


def _read_json_file(path: Path, max_bytes: int) -> Any | None:
    size = path.stat().st_size
    if size > max_bytes:
        raise ProbeError(
            f"refusing JSON file larger than {max_bytes} bytes; "
            "increase --max-json-mb explicitly if this is expected"
        )
    raw = path.read_bytes()
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def load_documents(source: Path, max_bytes: int) -> tuple[list[Any], int]:
    if source.is_file() and zipfile.is_zipfile(source):
        return _json_documents_from_zip(source, max_bytes)

    if source.is_file():
        suffix = source.suffix.lower()
        if suffix in {".html", ".htm"}:
            return [], 1
        if suffix != ".json":
            raise ProbeError("source must be a .zip, .json, or directory")
        document = _read_json_file(source, max_bytes)
        return ([document] if document is not None else []), 0

    if source.is_dir():
        documents: list[Any] = []
        html_count = 0
        for path in source.rglob("*"):
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in {".html", ".htm"}:
                html_count += 1
            elif suffix == ".json":
                document = _read_json_file(path, max_bytes)
                if document is not None:
                    documents.append(document)
        return documents, html_count

    raise ProbeError("source path does not exist")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_probe(
    *,
    provider: str,
    source: Path,
    sentinel: str,
    output: Path,
    max_json_mb: int,
) -> dict[str, Any]:
    if not sentinel or len(sentinel) < 12:
        raise ProbeError("sentinel must be at least 12 characters and deliberately non-sensitive")
    if max_json_mb <= 0:
        raise ProbeError("--max-json-mb must be positive")

    documents, html_count = load_documents(source, max_json_mb * 1024 * 1024)
    matches: list[dict[str, Any]] = []
    for document in documents:
        matches.extend(_find_records(document, provider, sentinel))

    if not documents:
        raise ProbeError(
            f"no readable JSON documents found (HTML documents seen: {html_count}); "
            "this probe validates the JSON adapter path only"
        )
    if len(matches) != 1:
        raise ProbeError(
            f"expected exactly one {provider} record containing the sentinel; found {len(matches)}"
        )

    specimen = sanitize(matches[0], sentinel)
    encoded = (json.dumps(specimen, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if sentinel.encode("utf-8") not in encoded:
        raise ProbeError("sanitized specimen unexpectedly lost the sentinel")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(encoded)

    return {
        "ok": True,
        "provider": provider,
        "json_documents_scanned": len(documents),
        "html_documents_seen": html_count,
        "matched_records": 1,
        "sanitized_specimen_sha256": _sha256_bytes(encoded),
        "sanitized_specimen_bytes": len(encoded),
        "output_file": output.name,
        "raw_export_not_copied": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a structurally useful, redacted specimen from a real provider export."
    )
    parser.add_argument("provider", choices=["claude", "gemini"])
    parser.add_argument("source", help="local provider export ZIP, JSON file, or extracted directory")
    parser.add_argument("--sentinel", required=True, help="deliberately non-sensitive unique test marker")
    parser.add_argument(
        "-o",
        "--output",
        default="paic-real-export-probe.sanitized.json",
        help="sanitized JSON specimen to create",
    )
    parser.add_argument("--max-json-mb", type=int, default=256)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_probe(
            provider=args.provider,
            source=Path(args.source),
            sentinel=args.sentinel,
            output=Path(args.output),
            max_json_mb=args.max_json_mb,
        )
    except (ProbeError, OSError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
