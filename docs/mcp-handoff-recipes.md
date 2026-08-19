# MCP handoff recipes: Claude Code, Codex, and Cursor

Portable AI Context exposes a local stdio MCP server with:

```text
paic mcp --root <workspace>
```

This document shows conservative ways to connect that server to Claude Code, Codex, and Cursor.

These are **handoff/configuration recipes**, not a new MCP security model. The PAIC server still owns its filesystem boundary:

```text
host launches PAIC
        ↓
paic mcp --root <explicit workspace>
        ↓
PAIC validates root-relative source paths and resolved containment
        ↓
content-free inspect/conform or server-owned derived artifacts
```

Host workspace permissions, MCP Roots, approval prompts, or editor sandbox settings can add defense in depth, but they do not replace PAIC's explicit `--root` enforcement.

## Before connecting a host

Install PAIC with the optional MCP dependency in an environment the host process can launch:

```bash
pip install 'portable-ai-context[mcp]'
```

Confirm the command is available:

```bash
paic --version
paic mcp --help
```

Choose the smallest workspace root that contains the conversation artifacts you actually want PAIC to inspect. Avoid using your home directory or a broad drive root merely for convenience.

If the host cannot find `paic`, use the full path to the installed `paic` executable in that host's configuration. GUI applications do not always inherit the same `PATH` as an interactive terminal.

On Windows, a forward-slash absolute root such as `D:/Projects/example` is often easier to place in JSON/TOML than a backslash path that requires escaping. Use a path that resolves to the intended local workspace on your machine.

The examples committed under [`examples/mcp/`](../examples/mcp/) are deliberately inert `.example` files. Copy and review them; do not treat the repository itself as permission to install or approve an MCP server.

## Codex

OpenAI's current Codex MCP documentation supports local STDIO servers and the CLI form:

```text
codex mcp add <server-name> -- <stdio-server-command>
```

It also supports MCP configuration in `~/.codex/config.toml`, or `.codex/config.toml` for a trusted project. The ChatGPT desktop app, Codex CLI, and Codex IDE extension share MCP configuration for the same Codex host. ChatGPT web does **not** read local Codex configuration.

Official reference:

- https://developers.openai.com/codex/mcp

### Conservative CLI registration

Replace the placeholder with an explicit local root:

```bash
codex mcp add paic -- paic mcp --root /ABSOLUTE/PATH/TO/WORKSPACE
```

Then verify the configured server:

```bash
codex mcp list
```

Inside the Codex TUI, use:

```text
/mcp
```

The registration command must launch PAIC as a **local stdio process**. Do not replace it with an HTTP URL for the current PAIC alpha.

### Equivalent `config.toml`

The inert repository example is [`examples/mcp/codex.config.toml.example`](../examples/mcp/codex.config.toml.example):

```toml
[mcp_servers.paic]
command = "paic"
args = ["mcp", "--root", "/ABSOLUTE/PATH/TO/WORKSPACE"]
```

For a machine-wide personal configuration, review and merge the entry into your own `~/.codex/config.toml`. For a project-scoped configuration, Codex documents `.codex/config.toml` for trusted projects; do not assume a newly cloned untrusted project should be allowed to launch local tooling automatically.

Codex supports additional MCP approval and tool-filter settings. Those may be useful as defense in depth, but this recipe does not depend on them for PAIC path authorization.

## Claude Code

Anthropic's current Claude Code MCP reference supports local stdio servers with:

```text
claude mcp add [options] <name> -- <command> [args...]
```

The `--` separator is important: arguments after it are passed to the local MCP server rather than parsed as Claude Code options.

Official reference:

- https://code.claude.com/docs/en/mcp

### Recommended default: local scope

For a machine-specific absolute workspace root, use local scope so the configuration stays private to the current project/user environment instead of being committed for every clone:

```bash
claude mcp add --transport stdio --scope local paic -- \
  paic mcp --root /ABSOLUTE/PATH/TO/WORKSPACE
```

Verify it with:

```bash
claude mcp get paic
claude mcp list
```

Inside Claude Code, `/mcp` shows server status.

Claude Code's current documentation reports statuses such as connected, pending approval, or failed. A successful `claude mcp add` means the configuration was written; use the status commands to verify that the server actually connected.

### Optional project `.mcp.json`

The inert repository example is [`examples/mcp/claude.mcp.json.example`](../examples/mcp/claude.mcp.json.example):

```json
{
  "mcpServers": {
    "paic": {
      "type": "stdio",
      "command": "paic",
      "args": ["mcp", "--root", "/ABSOLUTE/PATH/TO/WORKSPACE"]
    }
  }
}
```

If you intentionally turn this into a real project-level `.mcp.json`, review the absolute root for each machine before sharing it.

Claude Code applies workspace trust and project-server approval to project `.mcp.json` files. Current Anthropic documentation explicitly notes that a cloned repository cannot silently approve its own project MCP server. Do not add tracked settings intended to bypass that approval step.

Claude Code also exposes `CLAUDE_PROJECT_DIR` and MCP Roots information to servers in some workflows. PAIC does **not** use either mechanism as its authorization boundary: the root passed to `paic mcp --root ...` remains authoritative.

## Cursor

Cursor's current MCP documentation supports local `stdio` servers in `mcp.json` and documents these configuration locations:

```text
project: .cursor/mcp.json
global:  ~/.cursor/mcp.json
```

Cursor also supports `${workspaceFolder}` interpolation in `command`, `args`, and other MCP configuration fields.

Official reference:

- https://cursor.com/docs/mcp

### Project configuration

For a project-specific PAIC root, `${workspaceFolder}` avoids committing a machine-specific absolute path:

```json
{
  "mcpServers": {
    "paic": {
      "type": "stdio",
      "command": "paic",
      "args": ["mcp", "--root", "${workspaceFolder}"]
    }
  }
}
```

The inert repository copy is [`examples/mcp/cursor.mcp.json.example`](../examples/mcp/cursor.mcp.json.example).

If you decide to activate it, create/review `.cursor/mcp.json` in the project yourself. This repository intentionally does not commit an active `.cursor/mcp.json` merely to self-install PAIC.

Cursor documents approval before MCP tool use by default and exposes MCP server management through its Customize UI. For connection diagnostics, open the Output panel and select **MCP Logs**.

### Global configuration

For `~/.cursor/mcp.json`, use an explicit root rather than `${workspaceFolder}` when you want the PAIC server to be tied to one fixed workspace:

```json
{
  "mcpServers": {
    "paic": {
      "type": "stdio",
      "command": "paic",
      "args": ["mcp", "--root", "/ABSOLUTE/PATH/TO/WORKSPACE"]
    }
  }
}
```

Do not add `url`, OAuth, authorization headers, or API keys for PAIC's current stdio-only server.

## What a successful host connection should expose

The current PAIC MCP alpha exposes exactly four tools:

```text
inspect_source
conform_source
build_checkpoint
build_redaction_review
```

and zero MCP resources.

A host-specific smoke, when intentionally performed, should record only non-sensitive facts such as:

```text
host/version
server connected: yes/no
tool count: 4
resource count: 0
content-free inspect/conform succeeded: yes/no
```

Do not publish the absolute workspace root, source path, conversation title/text, checkpoint text, or redaction artifact contents as connectivity evidence.

## Capabilities these recipes do not add

Connecting PAIC to a host does not add:

```text
arbitrary read_file/list_directory
raw conversation resources
paic compile through MCP
provider/API network calls
shell/subprocess tools
remote HTTP/SSE PAIC transport
arbitrary output paths
```

The host may have its own unrelated filesystem, terminal, browser, or network tools. Those are outside PAIC's MCP server contract and must not be confused with permissions granted by PAIC.

## Validation status

Repository CI statically validates the three inert examples and their security shape. On Python 3.11+ the Codex TOML example is parsed with the standard-library `tomllib`; Python 3.10 uses a strict exact-template check because `tomllib` is not part of that runtime's standard library. Claude/Cursor JSON examples are parsed with the standard-library `json` module on every supported Python version.

This proves that the committed recipes are syntactically/structurally constrained as documented. It is **not** evidence that the current installed versions of Claude Code, Codex, and Cursor were all launched and live-smoke-tested against PAIC. Any such live-host evidence must be recorded separately and content-free.
