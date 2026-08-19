from __future__ import annotations

from pathlib import Path
import re

from portable_ai_context.compact_format import FORMAT_HEADER, unescape_message_text
from portable_ai_context.errors import ParseError
from portable_ai_context.models import Conversation, Message, SourceInfo
from portable_ai_context.utils import source_fingerprint


V1_MARKER_RE = re.compile(r"^<<<(USER|ASSISTANT)>>>\s*$", re.MULTILINE)
LEGACY_MARKER_RE = re.compile(r"^<<<(USER|ASSISTANT)>>>{0,1}\s*$", re.MULTILINE)


def can_load(text: str) -> bool:
    return "<<<USER>>>" in text or "<<<ASSISTANT>>>" in text


def load(source: str, text: str) -> Conversation:
    header_lines = text.splitlines()[:20]
    compact_v1 = FORMAT_HEADER in header_lines
    marker_re = V1_MARKER_RE if compact_v1 else LEGACY_MARKER_RE

    title = ""
    for line in header_lines:
        if line.startswith("TITLE:"):
            title = line[len("TITLE:"):].strip()
            break

    matches = list(marker_re.finditer(text))
    messages: list[Message] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if compact_v1 and body:
            body = unescape_message_text(body)
        if body:
            messages.append(
                Message(role=match.group(1).lower(), text=body, index=len(messages))
            )

    if not messages:
        raise ParseError("compact TXT contains no message markers")

    return Conversation(
        title=title,
        messages=messages,
        source=SourceInfo(
            kind="compact_txt",
            locator=str(Path(source)),
            fingerprint=source_fingerprint(text),
            metadata={"format": "paic-compact-v1" if compact_v1 else "legacy-marker-text"},
        ),
    )
