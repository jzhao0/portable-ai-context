# Root-confined MCP server alpha

Portable AI Context can expose a small set of local orchestration tools to MCP-capable hosts through the official Python MCP SDK v2.

The alpha is intentionally narrow:

- stdio transport only;
- one explicit local workspace root;
- no arbitrary file read/list tool;
- no compiler/provider/network tool;
- no shell execution;
- no arbitrary output path;
- no MCP resource that exposes source/artifact text.

This is a PAIC workflow server, not a general filesystem MCP server.

## Installation

The base package remains dependency-free. MCP support is optional:

```bash
pip install 'portable-ai-context[mcp]'
```

The optional extra uses the official stable Python MCP SDK v2 line:

```text
mcp>=2.0,<3
```

## Start the server

```bash
paic mcp --root /path/to/workspace
```

`--root` is mandatory.

The alpha calls the official SDK with:

```text
transport="stdio"
```

No HTTP/SSE listener is started. Stdout is reserved for the MCP protocol wire; PAIC does not print a startup banner or JSON status line before serving.

## Why PAIC does not rely on MCP Roots for authorization

The current MCP specification has deprecated the Roots feature, and the Python SDK does not automatically enforce a client-provided roots list as a filesystem security boundary.

PAIC therefore owns its authorization boundary independently:

```text
server launch --root
        ↓
PAIC path policy
        ↓
allowed local source / server-owned artifact area
```

A client-reported MCP root, tool annotation, or model instruction cannot expand the configured PAIC root.

Official references:

- https://modelcontextprotocol.io/specification/2026-07-28/client/roots
- https://github.com/modelcontextprotocol/python-sdk

## Source path contract

Tool inputs use root-relative paths with forward slashes, for example:

```text
research/conversation.jsonl
exports/project.aicb
```

The server rejects:

- absolute paths;
- `.` / `..` traversal components;
- backslashes / drive-style paths;
- NUL/control path input;
- resolved symlink escapes outside the configured root;
- directories/special files;
- unsupported source suffixes;
- source files above the MCP source-size limit.

Current allowed local suffixes are deliberately narrower than the standalone loader surface:

```text
.aicb
.jsonl
.json
.txt
.html
```

The current source-size ceiling is 64 MiB at the MCP boundary. Format-specific readers may impose additional limits.

ChatGPT shared URLs and other network sources are deliberately excluded from the MCP alpha even though the standalone PAIC CLI supports additional source types.

Model-visible errors use fixed categories and do not echo attempted paths, the absolute workspace root, parser body excerpts, or low-level OS exception text.

## Server-owned artifact area

MCP write tools do not accept an output path supplied by the model.

PAIC owns:

```text
<root>/.paic-mcp/
```

and creates a fresh unique directory per write operation:

```text
.paic-mcp/checkpoints/checkpoint-<random>/
.paic-mcp/redactions/redaction-<random>/
```

This prevents an MCP tool call from targeting an arbitrary user file for overwrite.

PAIC rejects the reserved artifact area/category if it is a symlink or non-directory. Newly created operation directories are checked to remain inside the configured root before source-derived bytes are written. If a newly created empty artifact directory fails a later containment check, PAIC removes that empty directory on a best-effort basis before returning the fixed error.

Returned artifact paths are root-relative POSIX-style strings. Absolute host filesystem paths are not returned to the model.

## Exposed tools

The alpha exposes exactly four tools.

### `inspect_source`

Input:

```text
source: root-relative local source
```

Returns structured, content-free information:

- source kind;
- message count;
- snapshot timestamp/raw-node count when available;
- integrity report/digests/tail hashes;
- privacy category counts.

It does **not** return:

- conversation title;
- source locator/path;
- message text/previews.

### `conform_source`

Runs the same content-free canonical/round-trip contract as `paic conform` and returns its structured report.

### `build_checkpoint`

Inputs:

```text
source
profile = lite | standard | full
```

Builds the deterministic no-AI checkpoint and writes:

```text
CHECKPOINT.md
checkpoint-report.json
```

under a fresh `.paic-mcp/checkpoints/...` directory.

The MCP tool result returns only root-relative artifact paths and the content-free checkpoint report. **Checkpoint markdown is not returned directly through the MCP tool result in this alpha.**

### `build_redaction_review`

Builds the existing pattern-limited redaction-review artifacts under a fresh `.paic-mcp/redactions/...` directory.

The tool returns only root-relative artifact paths plus the content-free redaction report.

The redaction semantics remain unchanged:

```text
manual_review_required = true
patterns_are_exhaustive = false
```

A zero supported-pattern rescan is not a universal share-safety guarantee.

## Deliberately absent capabilities

The MCP alpha does not expose:

```text
read_file
list_directory
raw conversation text
raw checkpoint/redaction artifact resource
paic compile
ChatGPT URL fetch
provider API call
shell/subprocess
arbitrary output path
source mutation
```

This means the model cannot use PAIC MCP itself to open an arbitrary file under the root or send a canonical conversation to a remote compiler provider.

A future handoff integration may add carefully scoped artifact resources, but that requires a separate privacy/security contract rather than silently broadening this server.

## Testing boundary

Normal cross-platform tests run with the base package and do not require MCP to be installed.

The package job uses an isolated environment and verifies:

1. the base built wheel does **not** install `mcp`;
2. `paic mcp --help` exists in the base CLI;
3. the same built wheel's `[mcp]` extra installs successfully;
4. the official SDK `Client(server)` connects in memory;
5. exactly the four alpha tools are exposed;
6. no resources are exposed;
7. inspect/conform results contain no fixture body/root path;
8. checkpoint/redaction writes stay under `.paic-mcp` and return only relative paths/reports;
9. a traversal attempt fails without echoing the attempted path;
10. no network listener/server is started during the smoke.

The in-memory SDK smoke validates MCP schemas/dispatch/structured results. It does not constitute a host-specific Claude Code/Codex/Cursor integration smoke; those remain separate handoff recipes/validation work.
