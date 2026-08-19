from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from pathlib import PurePosixPath
import stat
import tempfile

from .errors import PortableAIContextError


MCP_ARTIFACT_DIRNAME = ".paic-mcp"
MCP_MAX_SOURCE_BYTES = 64 * 1024 * 1024
MCP_ALLOWED_SOURCE_SUFFIXES = frozenset(
    {".aicb", ".jsonl", ".json", ".txt", ".html"}
)
_MAX_RELATIVE_PATH_CHARS = 4096
_SAFE_ARTIFACT_CATEGORIES = frozenset({"checkpoints", "redactions"})


class MCPWorkspaceError(PortableAIContextError):
    """Content-safe workspace policy failure for MCP operations."""


def _remove_empty_directory(path: Path | None) -> None:
    if path is None:
        return
    try:
        if path.is_symlink():
            return
        path.rmdir()
    except OSError:
        pass


@dataclass(slots=True, frozen=True)
class MCPWorkspace:
    root: Path
    max_source_bytes: int = MCP_MAX_SOURCE_BYTES

    @classmethod
    def from_root(
        cls,
        root: str | os.PathLike[str],
        *,
        max_source_bytes: int = MCP_MAX_SOURCE_BYTES,
    ) -> "MCPWorkspace":
        if not isinstance(max_source_bytes, int) or isinstance(max_source_bytes, bool) or max_source_bytes <= 0:
            raise ValueError("max_source_bytes must be a positive integer")
        try:
            resolved = Path(root).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, TypeError) as exc:
            raise MCPWorkspaceError("MCP workspace root is unavailable") from exc
        if not resolved.is_dir():
            raise MCPWorkspaceError("MCP workspace root is unavailable")
        return cls(root=resolved, max_source_bytes=max_source_bytes)

    @staticmethod
    def _relative_parts(value: str) -> tuple[str, ...]:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > _MAX_RELATIVE_PATH_CHARS
            or value != value.strip()
            or "\\" in value
            or ":" in value
            or any(character.isspace() and character not in {" "} for character in value)
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise MCPWorkspaceError("MCP relative path is invalid")

        raw_parts = value.split("/")
        if any(part in {"", ".", ".."} for part in raw_parts):
            raise MCPWorkspaceError("MCP relative path is invalid")

        parsed = PurePosixPath(value)
        if parsed.is_absolute() or not parsed.parts:
            raise MCPWorkspaceError("MCP relative path is invalid")
        return tuple(parsed.parts)

    def _ensure_within_root(self, candidate: Path) -> Path:
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise MCPWorkspaceError("MCP path escapes the configured workspace root") from exc
        return resolved

    def resolve_source(self, relative_path: str) -> Path:
        parts = self._relative_parts(relative_path)
        suffix = Path(parts[-1]).suffix.lower()
        if suffix not in MCP_ALLOWED_SOURCE_SUFFIXES:
            raise MCPWorkspaceError("MCP source type is not supported")

        resolved = self._ensure_within_root(self.root.joinpath(*parts))
        try:
            info = resolved.stat()
        except OSError as exc:
            raise MCPWorkspaceError("MCP source is unavailable") from exc
        if not stat.S_ISREG(info.st_mode):
            raise MCPWorkspaceError("MCP source is unavailable")
        if info.st_size > self.max_source_bytes:
            raise MCPWorkspaceError("MCP source exceeds the configured size limit")
        return resolved

    def _artifact_root(self) -> Path:
        path = self.root / MCP_ARTIFACT_DIRNAME
        created_here = False
        try:
            if path.exists() or path.is_symlink():
                if path.is_symlink() or not path.is_dir():
                    raise MCPWorkspaceError("MCP artifact area is unavailable")
            else:
                path.mkdir(mode=0o700)
                created_here = True
            resolved = path.resolve(strict=True)
            resolved.relative_to(self.root)
        except MCPWorkspaceError:
            if created_here:
                _remove_empty_directory(path)
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            if created_here:
                _remove_empty_directory(path)
            raise MCPWorkspaceError("MCP artifact area is unavailable") from exc
        return resolved

    def create_artifact_directory(self, category: str) -> Path:
        if category not in _SAFE_ARTIFACT_CATEGORIES:
            raise ValueError("unsupported MCP artifact category")

        artifact_root = self._artifact_root()
        category_dir = artifact_root / category
        category_created_here = False
        created: Path | None = None
        try:
            if category_dir.exists() or category_dir.is_symlink():
                if category_dir.is_symlink() or not category_dir.is_dir():
                    raise MCPWorkspaceError("MCP artifact area is unavailable")
            else:
                category_dir.mkdir(mode=0o700)
                category_created_here = True
            category_resolved = category_dir.resolve(strict=True)
            category_resolved.relative_to(self.root)
            created = Path(tempfile.mkdtemp(prefix=f"{category[:-1]}-", dir=category_resolved))
            created_resolved = created.resolve(strict=True)
            created_resolved.relative_to(self.root)
        except MCPWorkspaceError:
            _remove_empty_directory(created)
            if category_created_here:
                _remove_empty_directory(category_dir)
            raise
        except (OSError, RuntimeError, ValueError) as exc:
            _remove_empty_directory(created)
            if category_created_here:
                _remove_empty_directory(category_dir)
            raise MCPWorkspaceError("MCP artifact area is unavailable") from exc
        return created_resolved

    def relative_display(self, path: str | os.PathLike[str]) -> str:
        try:
            resolved = Path(path).resolve(strict=True)
            relative = resolved.relative_to(self.root)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise MCPWorkspaceError("MCP artifact path is unavailable") from exc
        return relative.as_posix()
