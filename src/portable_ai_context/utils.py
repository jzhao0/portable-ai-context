from __future__ import annotations

import hashlib
import re
from pathlib import Path


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def source_fingerprint(value: str) -> str:
    return sha256_text(value)[:16]


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def read_text(path: str | Path) -> str:
    return Path(path).expanduser().resolve().read_text(encoding="utf-8", errors="replace")
