from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(slots=True)
class SourceInfo:
    kind: str
    locator: str | None = None
    fingerprint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SnapshotInfo:
    created_at: float | None = None
    updated_at: float | None = None
    raw_node_count: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Message:
    role: str
    text: str
    index: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Conversation:
    title: str
    messages: list[Message]
    source: SourceInfo
    snapshot: SnapshotInfo = field(default_factory=SnapshotInfo)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "source": asdict(self.source),
            "snapshot": asdict(self.snapshot),
            "metadata": self.metadata,
        }
