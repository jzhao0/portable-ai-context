from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile

from mcp import Client
from mcp.types import TextContent

from portable_ai_context.mcp_server import create_mcp_server


FAKE_SECRET = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
PRIVATE_MESSAGE_BODY = "PRIVATE_MCP_MESSAGE_BODY"
PRIVATE_ESCAPE = "PRIVATE_ESCAPE_PATH"


def _visible_text(result) -> str:
    return "\n".join(
        block.text for block in result.content if isinstance(block, TextContent)
    )


def _structured(result) -> dict:
    value = result.structured_content
    if not isinstance(value, dict):
        raise SystemExit("MCP tool did not return structured content")
    return value


async def _run() -> dict:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        source = root / "conversation.jsonl"
        source.write_text(
            "\n".join(
                [
                    json.dumps({"role": "user", "text": PRIVATE_MESSAGE_BODY}),
                    json.dumps({"role": "assistant", "text": "ordinary answer"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        redaction_source = root / "redaction.jsonl"
        redaction_source.write_text(
            "\n".join(
                [
                    json.dumps({"role": "user", "text": f"synthetic {FAKE_SECRET}"}),
                    json.dumps({"role": "assistant", "text": "ordinary answer"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        server = create_mcp_server(root)
        async with Client(server) as client:
            tools_result = await client.list_tools()
            tool_names = {tool.name for tool in tools_result.tools}
            expected_tools = {
                "inspect_source",
                "conform_source",
                "build_checkpoint",
                "build_redaction_review",
            }
            if tool_names != expected_tools:
                raise SystemExit(
                    f"unexpected MCP tool set: {sorted(tool_names)!r}"
                )

            resources_result = await client.list_resources()
            if resources_result.resources:
                raise SystemExit("PAIC MCP alpha unexpectedly exposed resources")

            inspect_result = await client.call_tool(
                "inspect_source", {"source": "conversation.jsonl"}
            )
            if inspect_result.is_error:
                raise SystemExit("MCP inspect_source unexpectedly failed")
            inspect_payload = _structured(inspect_result)
            inspect_serialized = json.dumps(inspect_payload, sort_keys=True)
            if PRIVATE_MESSAGE_BODY in inspect_serialized or str(root) in inspect_serialized:
                raise SystemExit("MCP inspect_source leaked source content/path")
            if inspect_payload.get("source_kind") != "jsonl":
                raise SystemExit("MCP inspect_source returned wrong source kind")
            if inspect_payload.get("message_count") != 2:
                raise SystemExit("MCP inspect_source returned wrong message count")

            conform_result = await client.call_tool(
                "conform_source", {"source": "conversation.jsonl"}
            )
            if conform_result.is_error:
                raise SystemExit("MCP conform_source unexpectedly failed")
            conform_payload = _structured(conform_result)
            conform_serialized = json.dumps(conform_payload, sort_keys=True)
            if PRIVATE_MESSAGE_BODY in conform_serialized or str(root) in conform_serialized:
                raise SystemExit("MCP conform_source leaked source content/path")
            if conform_payload.get("ok") is not True:
                raise SystemExit("MCP conform_source did not pass the valid fixture")

            checkpoint_result = await client.call_tool(
                "build_checkpoint",
                {"source": "conversation.jsonl", "profile": "lite"},
            )
            if checkpoint_result.is_error:
                raise SystemExit("MCP build_checkpoint unexpectedly failed")
            checkpoint_payload = _structured(checkpoint_result)
            checkpoint_serialized = json.dumps(checkpoint_payload, sort_keys=True)
            if PRIVATE_MESSAGE_BODY in checkpoint_serialized or str(root) in checkpoint_serialized:
                raise SystemExit("MCP build_checkpoint leaked source content/path")
            checkpoint_dir = checkpoint_payload.get("artifact_directory")
            if not isinstance(checkpoint_dir, str) or not checkpoint_dir.startswith(
                ".paic-mcp/checkpoints/checkpoint-"
            ):
                raise SystemExit("MCP checkpoint artifact directory is not root-relative/server-owned")
            checkpoint_artifacts = checkpoint_payload.get("artifacts")
            if not isinstance(checkpoint_artifacts, dict):
                raise SystemExit("MCP checkpoint artifact mapping is missing")
            for relative in checkpoint_artifacts.values():
                if not isinstance(relative, str) or not relative.startswith(checkpoint_dir + "/"):
                    raise SystemExit("MCP checkpoint artifact escaped its unique server directory")
                if not (root / relative).is_file():
                    raise SystemExit("MCP checkpoint artifact was not created")

            redaction_result = await client.call_tool(
                "build_redaction_review", {"source": "redaction.jsonl"}
            )
            if redaction_result.is_error:
                raise SystemExit("MCP build_redaction_review unexpectedly failed")
            redaction_payload = _structured(redaction_result)
            redaction_serialized = json.dumps(redaction_payload, sort_keys=True)
            if (
                FAKE_SECRET in redaction_serialized
                or str(root) in redaction_serialized
                or "synthetic" in redaction_serialized
            ):
                raise SystemExit("MCP redaction tool leaked source content/path")
            redaction_summary = redaction_payload.get("summary")
            if not isinstance(redaction_summary, dict):
                raise SystemExit("MCP redaction summary is missing")
            if redaction_summary.get("supported_patterns_remaining") != 0:
                raise SystemExit("MCP redaction left a supported pattern")
            if redaction_summary.get("manual_review_required") is not True:
                raise SystemExit("MCP redaction did not preserve manual-review requirement")
            if redaction_summary.get("patterns_are_exhaustive") is not False:
                raise SystemExit("MCP redaction overstated pattern exhaustiveness")
            redaction_dir = redaction_payload.get("artifact_directory")
            if not isinstance(redaction_dir, str) or not redaction_dir.startswith(
                ".paic-mcp/redactions/redaction-"
            ):
                raise SystemExit("MCP redaction artifact directory is not root-relative/server-owned")

            escape_result = await client.call_tool(
                "inspect_source", {"source": f"../{PRIVATE_ESCAPE}.jsonl"}
            )
            if escape_result.is_error is not True:
                raise SystemExit("MCP traversal attempt did not fail")
            escape_visible = _visible_text(escape_result)
            if PRIVATE_ESCAPE in escape_visible or str(root) in escape_visible:
                raise SystemExit("MCP traversal error echoed the attempted path/root")
            if "configured MCP workspace" not in escape_visible:
                raise SystemExit("MCP traversal error did not use the safe workspace category")

        return {
            "ok": True,
            "tools": sorted(expected_tools),
            "resources": 0,
            "inspect_content_free": True,
            "conform_content_free": True,
            "checkpoint_server_owned": True,
            "redaction_server_owned": True,
            "traversal_error_content_safe": True,
        }


def main() -> int:
    result = asyncio.run(_run())
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
