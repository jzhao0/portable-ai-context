# Anthropic Messages compiler backend

Portable AI Context can compile migration artifacts directly through Anthropic's non-streaming Messages API without installing the Anthropic Python SDK.

The backend identifier is:

```text
anthropic
```

## CLI

Example shape:

```bash
paic compile conversation.clean.html \
  --backend anthropic \
  --api-key-env ANTHROPIC_API_KEY \
  --map-model <map-model> \
  --final-model <final-model> \
  --anthropic-max-tokens 4096 \
  -o migration
```

PAIC deliberately does not hardcode a Claude model name. Model IDs change independently of the portability/compiler contract, so callers supply both map and final model names explicitly.

If `--api-base` is omitted for this backend, PAIC uses:

```text
https://api.anthropic.com
```

A custom base can be supplied for a compatible gateway. Bases ending in `/v1` are normalized so PAIC sends to exactly one `/v1/messages` path rather than duplicating `/v1`.

The global `--api-key-env` option is unchanged. It defaults to `PAIC_API_KEY` for backward compatibility with the existing compiler CLI. To use Anthropic's conventional environment-variable name, pass:

```text
--api-key-env ANTHROPIC_API_KEY
```

The key value is resolved at backend-construction time and is not stored in `BackendConfig`.

## Messages API mapping

The alpha transport uses the stable non-streaming Messages API shape:

```text
POST /v1/messages
Content-Type: application/json
X-Api-Key: <resolved key>
anthropic-version: 2023-06-01
```

PAIC maps one compiler completion call as:

```json
{
  "model": "<caller supplied model>",
  "max_tokens": 4096,
  "system": "<compiler system prompt>",
  "messages": [
    {"role": "user", "content": "<compiler user prompt>"}
  ],
  "stream": false,
  "temperature": 0.1
}
```

Anthropic's Messages API uses a top-level `system` parameter; PAIC does not send a `system`-role message.

The API version is intentionally explicit rather than relying on SDK behavior. Anthropic requires the `anthropic-version` header, and the alpha transport pins `2023-06-01`. Future API-version changes should be reviewed deliberately rather than silently changing request semantics.

Official references:

- https://platform.claude.com/docs/en/api/messages/create
- https://platform.claude.com/docs/en/api/versioning

## `max_tokens`

The Messages API requires a bounded output limit and different Claude models can support different maximum values.

PAIC therefore uses a conservative compiler default:

```text
--anthropic-max-tokens 4096
```

The value must be a positive integer and can be overridden by the caller. It applies independently to each map/merge/final/budget completion request.

If Anthropic reports `stop_reason: max_tokens`, PAIC fails the compiler call instead of silently accepting a truncated checkpoint or migration prompt.

## Response handling

A non-streaming Anthropic Message returns a typed `content` array. PAIC only accepts text content as compiler output:

```json
{
  "content": [
    {"type": "text", "text": "..."}
  ],
  "stop_reason": "end_turn"
}
```

When multiple text blocks are present, PAIC joins them in order with newline separators.

Non-text blocks are not turned into migration text. In particular, PAIC does not expose thinking blocks, tool-use blocks, or refusal payloads through the compiler output.

The alpha backend accepts successful `end_turn` and `stop_sequence` outcomes. It fails closed for:

```text
max_tokens
refusal
model_context_window_exceeded
tool_use
pause_turn
unknown future stop reasons
```

This is intentional: a migration compiler should not silently persist an incomplete or non-text provider outcome as if it were a complete handoff artifact.

## Error and privacy boundary

Normal PAIC compiler errors do not include:

- API-key values;
- source/system/user prompts;
- raw Anthropic response bodies;
- provider URLs;
- low-level transport error text;
- thinking/refusal content.

The user-facing categories are concise, for example:

```text
anthropic backend HTTP status 429
anthropic backend transport failed
anthropic backend returned invalid JSON
unexpected Anthropic response shape
anthropic backend returned no text content
anthropic backend output reached max_tokens
anthropic backend returned an unsupported stop reason
```

Underlying Python exceptions are chained when applicable for local debugging, but the normal CLI only prints the safe `CompilerError` message.

## Deliberate non-features

The alpha compiler backend does not enable:

- streaming;
- prompt caching;
- tools;
- images or PDFs;
- web search;
- extended thinking;
- beta headers;
- model auto-selection.

Those features are not required to satisfy the compiler protocol and would expand the transport/security contract.

## Validation boundary

CI uses deterministic mocked HTTP responses and the full cross-platform package/test matrix. It does **not** require or spend a live Anthropic API key.

A real paid API smoke is a separate validation activity and should only be performed when a user explicitly supplies/authorizes a key and intends to incur API usage.