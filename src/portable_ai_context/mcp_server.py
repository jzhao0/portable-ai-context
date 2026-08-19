from __future__ import annotations

import importlib
import json
from pathlib import Path
import shutil
from typing import Any, Literal

from . import __version__
from .adapters import load_conversation
from .checkpoint import build_extractive_checkpoint
from .conformance import inspect_conformance
from .errors import PortableAIContextError
from .integrity import inspect as inspect_integrity
from .mcp_workspace import MCPWorkspace, MCPWorkspaceError
from .privacy import inspect_conversation
from .redaction import write_redaction_review


MCP_SERVER_NAME = "portable-ai-context"


def _mcp_server_class():
    try:
        module = importlib.import_module("mcp.server")
        server_class = getattr(module, "MCPServer")
    except (ImportError, AttributeError) as exc:
        raise PortableAIContextError(
            "MCP server support is unavailable; install portable-ai-context[mcp]"
        ) from exc
    if not callable(server_class):
        raise PortableAIContextError(
            "MCP server support is unavailable; install portable-ai-context[mcp]"
        )
    return server_class


def _load_allowed_source(workspace: MCPWorkspace, source: str):
    try:
        path = workspace.resolve_source(source)
    except MCPWorkspaceError as exc:
        raise RuntimeError(
            "PAIC source is not allowed by the configured MCP workspace"
        ) from exc
    try:
        return load_conversation(str(path))
    except Exception as exc:
        raise RuntimeError(
            "PAIC source could not be loaded as a supported local conversation"
        ) from exc


def _relative_artifacts(workspace: MCPWorkspace, paths: dict[str, Path]) -> dict[str, str]:
    try:
        return {name: workspace.relative_display(path) for name, path in paths.items()}
    except MCPWorkspaceError as exc:
        raise RuntimeError("PAIC MCP artifact paths could not be reported safely") from exc


def create_mcp_server(root: str | Path):
    """Create the optional stdio MCP server without starting a transport."""
    server_class = _mcp_server_class()
    workspace = MCPWorkspace.from_root(root)
    server = server_class(MCP_SERVER_NAME, version=__version__)

    @server.tool()
    def inspect_source(source: str) -> dict[str, Any]:
        """Inspect one root-confined local PAIC source without returning message text or title."""
        conversation = _load_allowed_source(workspace, source)
        try:
            integrity = inspect_integrity(conversation)
            privacy = inspect_conversation(conversation)
            return {
                "source_kind": conversation.source.kind,
                "message_count": len(conversation.messages),
                "snapshot": {
                    "updated_at": conversation.snapshot.updated_at,
                    "raw_node_count": conversation.snapshot.raw_node_count,
                },
                "integrity": integrity.to_dict(),
                "privacy": privacy.to_dict(),
            }
        except Exception as exc:
            raise RuntimeError("PAIC source inspection failed safely") from exc

    @server.tool()
    def conform_source(source: str) -> dict[str, Any]:
        """Run the content-free PAIC conformance report for one root-confined local source."""
        conversation = _load_allowed_source(workspace, source)
        try:
            return inspect_conformance(conversation).to_dict()
        except Exception as exc:
            raise RuntimeError("PAIC source conformance failed safely") from exc

    @server.tool()
    def build_checkpoint(
        source: str,
        profile: Literal["lite", "standard", "full"] = "standard",
    ) -> dict[str, Any]:
        """Write a deterministic checkpoint under the server-owned artifact area."""
        conversation = _load_allowed_source(workspace, source)
        artifact_dir: Path | None = None
        try:
            artifact_dir = workspace.create_artifact_directory("checkpoints")
            result = build_extractive_checkpoint(conversation, profile=profile)
            checkpoint_path = artifact_dir / "CHECKPOINT.md"
            report_path = artifact_dir / "checkpoint-report.json"
            checkpoint_path.write_text(result.markdown, encoding="utf-8")
            report_path.write_text(
                json.dumps(
                    result.report.to_dict(),
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            artifacts = _relative_artifacts(
                workspace,
                {
                    "checkpoint": checkpoint_path,
                    "report": report_path,
                },
            )
            return {
                "artifact_directory": workspace.relative_display(artifact_dir),
                "artifacts": artifacts,
                "summary": result.report.to_dict(),
            }
        except Exception as exc:
            if artifact_dir is not None:
                shutil.rmtree(artifact_dir, ignore_errors=True)
            raise RuntimeError("PAIC checkpoint artifact could not be created safely") from exc

    @server.tool()
    def build_redaction_review(source: str) -> dict[str, Any]:
        """Write a pattern-limited redaction review under the server-owned artifact area."""
        conversation = _load_allowed_source(workspace, source)
        artifact_dir: Path | None = None
        try:
            artifact_dir = workspace.create_artifact_directory("redactions")
            paths = write_redaction_review(conversation, artifact_dir)
            report = json.loads(paths["redaction_report"].read_text(encoding="utf-8"))
            return {
                "artifact_directory": workspace.relative_display(artifact_dir),
                "artifacts": _relative_artifacts(workspace, paths),
                "summary": report,
            }
        except Exception as exc:
            if artifact_dir is not None:
                shutil.rmtree(artifact_dir, ignore_errors=True)
            raise RuntimeError(
                "PAIC redaction-review artifact could not be created safely"
            ) from exc

    return server


def run_mcp_stdio(root: str | Path) -> None:
    """Run the PAIC MCP server over stdio only."""
    server = create_mcp_server(root)
    server.run(transport="stdio")
