from __future__ import annotations

from datetime import datetime
from html.parser import HTMLParser
import json
from pathlib import Path
from typing import Any

from portable_ai_context.errors import ParseError
from portable_ai_context.models import Conversation, Message, SnapshotInfo, SourceInfo
from portable_ai_context.privacy import inspect_raw_text
from portable_ai_context.utils import normalize_text, source_fingerprint


GEMINI_PRODUCT_NAMES = {"gemini", "gemini apps"}
PROMPT_PREFIXES = ("Prompted: ", "Prompted ")
BLOCK_TAGS = {"p", "div", "pre", "li", "tr", "section", "article", "blockquote"}


class _HtmlTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return normalize_text("".join(self.parts))


def _label(value: Any) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def _activity_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _is_gemini_record(record: dict[str, Any]) -> bool:
    if _label(record.get("header")) in GEMINI_PRODUCT_NAMES:
        return True
    products = record.get("products")
    if isinstance(products, list):
        return any(_label(item) in GEMINI_PRODUCT_NAMES for item in products)
    return False


def _timestamp(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw).timestamp()
    except ValueError:
        return None


def _prompt_text(record: dict[str, Any]) -> str:
    title = record.get("title")
    if not isinstance(title, str):
        return ""
    for prefix in PROMPT_PREFIXES:
        if title.startswith(prefix):
            return title[len(prefix) :].strip()
    return ""


def _html_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    parser = _HtmlTextExtractor()
    parser.feed(value)
    parser.close()
    return parser.text()


def _response_text(record: dict[str, Any]) -> str:
    raw = record.get("safeHtmlItem")
    items = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = _html_text(item.get("html"))
        if text:
            parts.append(text)
    return normalize_text("\n".join(parts))


def _has_supported_content(record: dict[str, Any]) -> bool:
    return bool(_prompt_text(record) or _response_text(record))


def can_load(text: str) -> bool:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return False
    return any(
        _is_gemini_record(record) and _has_supported_content(record)
        for record in _activity_records(value)
    )


def load(source: str, text: str) -> Conversation:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError("invalid Gemini My Activity JSON") from exc

    source_records = _activity_records(value)
    gemini_records = [record for record in source_records if _is_gemini_record(record)]
    if not gemini_records:
        raise ParseError("Gemini My Activity JSON contains no Gemini Apps activity records")

    ordered: list[tuple[float | None, int, dict[str, Any]]] = [
        (_timestamp(record.get("time")), index, record)
        for index, record in enumerate(gemini_records)
    ]
    ordered.sort(
        key=lambda item: (
            item[0] is None,
            item[0] if item[0] is not None else 0.0,
            item[1],
        )
    )

    messages: list[Message] = []
    for _, _, record in ordered:
        prompt = _prompt_text(record)
        response = _response_text(record)
        if prompt:
            messages.append(Message(role="user", text=prompt, index=len(messages)))
        if response:
            messages.append(Message(role="assistant", text=response, index=len(messages)))

    if not messages:
        raise ParseError("Gemini activity records contain no supported prompt/response text")

    timestamps = [item[0] for item in ordered if item[0] is not None]
    headers = [
        record.get("header").strip()
        for _, _, record in ordered
        if isinstance(record.get("header"), str) and record.get("header").strip()
    ]
    title = headers[0] if headers and all(header == headers[0] for header in headers) else "Gemini Apps Activity"

    return Conversation(
        title=title or "Gemini Apps Activity",
        messages=messages,
        source=SourceInfo(
            kind="gemini_my_activity_json",
            locator=str(Path(source)),
            fingerprint=source_fingerprint(text),
            metadata={
                "format": "google_my_activity_gemini_json",
                "source_record_count": len(source_records),
                "activity_record_count": len(gemini_records),
                "runtime_marker_counts": inspect_raw_text(text),
            },
        ),
        snapshot=SnapshotInfo(
            created_at=min(timestamps) if timestamps else None,
            updated_at=max(timestamps) if timestamps else None,
            raw_node_count=len(gemini_records),
            metadata={
                "thread_reconstruction": "not_available_from_supported_activity_stream",
                "missing_timestamp_records": sum(1 for timestamp, _, _ in ordered if timestamp is None),
            },
        ),
    )
