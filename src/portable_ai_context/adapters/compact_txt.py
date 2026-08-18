from __future__ import annotations

from pathlib import Path
import re

from portable_ai_context.errors import ParseError
from portable_ai_context.models import Conversation, Message, SourceInfo
from portable_ai_context.utils import source_fingerprint


MARKER_RE = re.compile(r"^<<<(USER|ASSISTANT)>>>{0,1}\s*$", re.MULTILINE)


def can_load(text: str) -> bool:
    return "<<<USER>>>" in text or "<<<ASSISTANT>>>" in text


def load(source: str, text: str) -> Conversation:
    title = ""
    for line in text.splitlines()[:20]:
        if line.startswith("TITLE:"):
            title = line[len("TITLE:"):].strip()
            break

    matches = list(MARKER_RE.finditer(text))
    messages: list[Message] = []
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
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
        ),
    )
