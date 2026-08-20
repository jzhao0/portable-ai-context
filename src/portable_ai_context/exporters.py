from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import zipfile

from .bundle_contract import AICB_MEMBER_ORDER, AICB_SCHEMA_VERSION
from .compact_format import FORMAT_HEADER as COMPACT_FORMAT_HEADER, escape_message_text
from .integrity import inspect as inspect_integrity
from .models import Conversation
from .privacy import inspect_conversation
from .utils import normalize_text


CLEAN_FORMAT = "chatgpt-migrator-clean-v1"


def clean_html(conversation: Conversation) -> str:
    data = {
        "format": CLEAN_FORMAT,
        "title": conversation.title,
        "messages": [{"role": m.role, "text": m.text} for m in conversation.messages],
    }
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    body = []
    for message in conversation.messages:
        body.extend([
            f'<article class="message" data-index="{message.index}" data-role="{html.escape(message.role)}">',
            f"<h2>{html.escape(message.role.upper())}</h2>",
            f"<pre>{html.escape(message.text)}</pre>",
            "</article>",
        ])
    return "\n".join([
        "<!doctype html>", '<html lang="en"><head><meta charset="utf-8">',
        f"<title>{html.escape(conversation.title or 'AI Conversation')}</title>",
        '<meta name="archive-policy" content="title-user-assistant-final-text-only">',
        "</head><body>",
        f"<h1>{html.escape(conversation.title or 'AI Conversation')}</h1>",
        *body,
        '<script type="application/json" id="chatgpt-migrator-clean-data">',
        payload,
        "</script>",
        "</body></html>",
        "",
    ])


def compact_txt(conversation: Conversation) -> str:
    lines = [
        COMPACT_FORMAT_HEADER,
        f"TITLE: {conversation.title or '(untitled)'}",
        f"MESSAGES: {len(conversation.messages)}",
        "POLICY: canonical user/assistant final text; compact-v1 marker escaping.",
        "",
    ]
    for message in conversation.messages:
        body = escape_message_text(normalize_text(message.text))
        lines.extend([f"<<<{message.role.upper()}>>>", body, ""])
    return "\n".join(lines)


def jsonl(conversation: Conversation) -> str:
    return "".join(
        json.dumps({"role": m.role, "text": m.text}, ensure_ascii=False) + "\n"
        for m in conversation.messages
    )


def write_standard(conversation: Conversation, out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "clean_html": out / "conversation.clean.html",
        "compact_txt": out / "conversation.compact.txt",
        "jsonl": out / "conversation.clean.jsonl",
        "integrity": out / "integrity.json",
        "privacy": out / "privacy.json",
    }
    paths["clean_html"].write_text(clean_html(conversation), encoding="utf-8")
    paths["compact_txt"].write_text(compact_txt(conversation), encoding="utf-8")
    paths["jsonl"].write_text(jsonl(conversation), encoding="utf-8")
    paths["integrity"].write_text(json.dumps(inspect_integrity(conversation).to_dict(), indent=2), encoding="utf-8")
    paths["privacy"].write_text(json.dumps(inspect_conversation(conversation).to_dict(), indent=2), encoding="utf-8")
    return paths


def write_bundle(conversation: Conversation, output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    integrity = inspect_integrity(conversation)
    privacy = inspect_conversation(conversation)
    manifest = {
        "schema_version": AICB_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "conversation": {
            "title": conversation.title,
            "message_count": len(conversation.messages),
            "digest": integrity.conversation_digest,
            "source_kind": conversation.source.kind,
        },
        "artifacts": list(AICB_MEMBER_ORDER),
    }
    payloads = {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2),
        "conversation.jsonl": jsonl(conversation),
        "integrity.json": json.dumps(integrity.to_dict(), indent=2),
        "privacy.json": json.dumps(privacy.to_dict(), indent=2),
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name in AICB_MEMBER_ORDER:
            z.writestr(name, payloads[name])
    return output