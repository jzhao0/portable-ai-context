from __future__ import annotations

from html.parser import HTMLParser
import json
import re
from pathlib import Path
from typing import Any, Iterable

from portable_ai_context.errors import ParseError
from portable_ai_context.models import Conversation, Message, SnapshotInfo, SourceInfo
from portable_ai_context.privacy import inspect_raw_text
from portable_ai_context.utils import source_fingerprint


SENTINELS = {-1: None, -2: None, -3: None, -4: None, -5: None, -6: None}
ENQUEUE_RE = re.compile(r'enqueue\(("(?:\\.|[^"\\])*")\)', re.S)


class ScriptCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.in_script = False
        self.attrs: dict[str, str | None] = {}
        self.buf: list[str] = []
        self.scripts: list[tuple[dict[str, str | None], str]] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            self.in_script = True
            self.attrs = dict(attrs)
            self.buf = []

    def handle_data(self, data):
        if self.in_script:
            self.buf.append(data)

    def handle_entityref(self, name):
        if self.in_script:
            self.buf.append(f"&{name};")

    def handle_charref(self, name):
        if self.in_script:
            self.buf.append(f"&#{name};")

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.in_script:
            self.scripts.append((self.attrs, "".join(self.buf)))
            self.in_script = False
            self.attrs = {}
            self.buf = []


class FlatTableResolver:
    def __init__(self, table: list[Any]) -> None:
        self.table = table
        self.memo: dict[int, Any] = {}

    def resolve(self, ref: Any) -> Any:
        if not isinstance(ref, int):
            return ref
        if ref < 0:
            return SENTINELS.get(ref)
        if ref in self.memo:
            return self.memo[ref]
        if ref >= len(self.table):
            return None

        value = self.table[ref]
        if isinstance(value, dict):
            out: dict[Any, Any] = {}
            self.memo[ref] = out
            for key, raw in value.items():
                if isinstance(key, str) and key.startswith("_") and key[1:].isdigit():
                    real_key = self.resolve(int(key[1:]))
                else:
                    real_key = key
                out[real_key] = self.resolve(raw) if isinstance(raw, int) else raw
            return out

        if isinstance(value, list):
            out_list: list[Any] = []
            self.memo[ref] = out_list
            out_list.extend(self.resolve(x) if isinstance(x, int) else x for x in value)
            return out_list

        return value


def can_load(text: str) -> bool:
    return "streamController.enqueue" in text and "linear_conversation" in text


def parse_stream_tables(page_html: str) -> list[list[Any]]:
    parser = ScriptCollector()
    parser.feed(page_html)
    tables: list[list[Any]] = []

    for attrs, script_text in parser.scripts:
        if attrs.get("id") == "client-bootstrap":
            continue
        if "streamController.enqueue" not in script_text:
            continue
        for match in ENQUEUE_RE.finditer(script_text):
            try:
                decoded = json.loads(match.group(1))
                if not decoded.lstrip().startswith("["):
                    continue
                value = json.loads(decoded)
            except Exception:
                continue
            if isinstance(value, list):
                tables.append(value)

    if not tables:
        raise ParseError("no ChatGPT share conversation stream found")
    return tables


def _number(value: Any) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def find_conversation(tables: list[list[Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for table_index, table in enumerate(tables):
        key_indices = [i for i, item in enumerate(table) if item == "linear_conversation"]
        if not key_indices:
            continue
        resolver = FlatTableResolver(table)
        for key_index in key_indices:
            encoded_key = f"_{key_index}"
            for item_index, item in enumerate(table):
                if not isinstance(item, dict) or encoded_key not in item:
                    continue
                linear = resolver.resolve(item[encoded_key])
                if not isinstance(linear, list) or not linear:
                    continue
                conv: dict[str, Any] = {"linear_conversation": linear}
                for raw_key, raw_value in item.items():
                    if isinstance(raw_key, str) and raw_key.startswith("_") and raw_key[1:].isdigit():
                        key = resolver.resolve(int(raw_key[1:]))
                    else:
                        key = raw_key
                    if key in {"title", "create_time", "update_time", "default_model_slug"}:
                        conv[key] = resolver.resolve(raw_value) if isinstance(raw_value, int) else raw_value
                conv["_candidate_table"] = table_index
                conv["_candidate_item"] = item_index
                candidates.append(conv)

    if not candidates:
        raise ParseError("linear_conversation not found")

    return max(
        candidates,
        key=lambda c: (
            _number(c.get("update_time")),
            len(c.get("linear_conversation", [])),
            _number(c.get("create_time")),
        ),
    )


def _strings_from_part(part: Any) -> Iterable[str]:
    if isinstance(part, str):
        yield part
        return
    if not isinstance(part, dict):
        return
    ctype = part.get("content_type")
    if ctype in {"text", "input_text", None} and isinstance(part.get("text"), str):
        yield part["text"]


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if not isinstance(content, dict):
        return ""
    ctype = content.get("content_type")
    if ctype not in {"text", "multimodal_text"}:
        return ""
    parts = content.get("parts")
    if isinstance(parts, list):
        return "\n".join(x for p in parts for x in _strings_from_part(p)).strip()
    if isinstance(content.get("text"), str):
        return content["text"].strip()
    return ""


def extract_messages(conv: dict[str, Any]) -> list[Message]:
    messages: list[Message] = []
    for node in conv.get("linear_conversation", []):
        if not isinstance(node, dict):
            continue
        msg = node.get("message")
        if not isinstance(msg, dict):
            continue
        author = msg.get("author")
        if not isinstance(author, dict):
            continue
        role = author.get("role")
        content = msg.get("content") if isinstance(msg.get("content"), dict) else {}
        ctype = content.get("content_type")
        keep = (
            role == "user" and ctype in {"text", "multimodal_text"}
        ) or (
            role == "assistant" and ctype == "text"
        )
        if not keep:
            continue
        text = _message_text(msg)
        if text:
            messages.append(Message(role=role, text=text, index=len(messages)))
    if not messages:
        raise ParseError("ChatGPT conversation contains no user/assistant final text")
    return messages


def load(source: str, text: str) -> Conversation:
    tables = parse_stream_tables(text)
    conv = find_conversation(tables)
    messages = extract_messages(conv)
    title = conv.get("title") if isinstance(conv.get("title"), str) else ""
    return Conversation(
        title=title,
        messages=messages,
        source=SourceInfo(
            kind="chatgpt_html",
            locator=str(Path(source)),
            fingerprint=source_fingerprint(text),
            metadata={
                "candidate_table": conv.get("_candidate_table"),
                "runtime_marker_counts": inspect_raw_text(text),
            },
        ),
        snapshot=SnapshotInfo(
            created_at=conv.get("create_time") if isinstance(conv.get("create_time"), (int, float)) else None,
            updated_at=conv.get("update_time") if isinstance(conv.get("update_time"), (int, float)) else None,
            raw_node_count=len(conv.get("linear_conversation", [])),
            metadata={"default_model_slug": conv.get("default_model_slug")},
        ),
    )
