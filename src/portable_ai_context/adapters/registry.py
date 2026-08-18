from __future__ import annotations

from pathlib import Path

from portable_ai_context.errors import UnsupportedSourceError
from portable_ai_context.models import Conversation
from portable_ai_context.utils import read_text
from . import chatgpt_share, chatgpt_html, claude_json, clean_html, compact_txt, gemini_activity_json, jsonl


def load_conversation(source: str) -> Conversation:
    if chatgpt_share.is_share_url(source):
        return chatgpt_share.load(source)

    path = Path(source).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise UnsupportedSourceError(f"source does not exist or is unsupported: {source}")

    text = read_text(path)
    suffix = path.suffix.lower()

    if suffix in {".jsonl", ".ndjson"}:
        return jsonl.load(str(path), text)

    if suffix == ".json":
        if claude_json.can_load(text):
            return claude_json.load(str(path), text)
        if gemini_activity_json.can_load(text):
            return gemini_activity_json.load(str(path), text)

    if suffix == ".txt" and compact_txt.can_load(text):
        return compact_txt.load(str(path), text)

    if suffix in {".html", ".htm"}:
        if clean_html.can_load(text):
            return clean_html.load(str(path), text)
        if chatgpt_html.can_load(text):
            return chatgpt_html.load(str(path), text)

    raise UnsupportedSourceError(f"no adapter recognized: {source}")
