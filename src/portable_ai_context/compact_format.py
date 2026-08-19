from __future__ import annotations

import re


FORMAT_HEADER = "FORMAT: paic-compact-v1"
_MARKER_WITH_SLASHES_RE = re.compile(
    r"^(?P<slashes>\\*)(?P<marker><<<(?:USER|ASSISTANT)>>>(?:\s*))$"
)
_ESCAPED_MARKER_RE = re.compile(
    r"^(?P<slashes>\\+)(?P<marker><<<(?:USER|ASSISTANT)>>>(?:\s*))$"
)


def escape_message_text(text: str) -> str:
    """Escape body lines that could be parsed as canonical message markers.

    One backslash is added before any exact marker line and before any existing
    run of backslashes immediately preceding an exact marker. The latter makes
    the transform reversible for source text that already begins with a slash.
    """
    lines: list[str] = []
    for line in text.split("\n"):
        if _MARKER_WITH_SLASHES_RE.fullmatch(line):
            line = "\\" + line
        lines.append(line)
    return "\n".join(lines)


def unescape_message_text(text: str) -> str:
    """Reverse one compact-v1 marker-escape backslash per matching body line."""
    lines: list[str] = []
    for line in text.split("\n"):
        if _ESCAPED_MARKER_RE.fullmatch(line):
            line = line[1:]
        lines.append(line)
    return "\n".join(lines)
