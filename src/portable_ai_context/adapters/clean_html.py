from __future__ import annotations

from html.parser import HTMLParser
import json
from pathlib import Path

from portable_ai_context.errors import ParseError
from portable_ai_context.models import Conversation, Message, SourceInfo
from portable_ai_context.utils import source_fingerprint


CLEAN_DATA_ID = "chatgpt-migrator-clean-data"
FORMAT = "chatgpt-migrator-clean-v1"


class _CleanParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.capture = False
        self.buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script" and dict(attrs).get("id") == CLEAN_DATA_ID:
            self.capture = True

    def handle_data(self, data):
        if self.capture:
            self.buf.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.capture:
            self.capture = False


def can_load(text: str) -> bool:
    return CLEAN_DATA_ID in text


def load(source: str, text: str) -> Conversation:
    parser = _CleanParser()
    parser.feed(text)
    raw = "".join(parser.buf).strip()
    if not raw:
        raise ParseError("clean HTML marker found but embedded data is empty")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseError("clean HTML embedded JSON is invalid") from exc

    if data.get("format") != FORMAT:
        raise ParseError(f"unsupported clean HTML format: {data.get('format')!r}")

    messages: list[Message] = []
    for item in data.get("messages", []):
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        body = item.get("text")
        if role not in {"user", "assistant"} or not isinstance(body, str) or not body.strip():
            continue
        messages.append(Message(role=role, text=body, index=len(messages)))

    if not messages:
        raise ParseError("clean HTML contains no user/assistant messages")

    return Conversation(
        title=data.get("title") if isinstance(data.get("title"), str) else "",
        messages=messages,
        source=SourceInfo(
            kind="clean_html",
            locator=str(Path(source)),
            fingerprint=source_fingerprint(text),
        ),
    )
