# Ollama / local compiler backend

Portable AI Context can compile migration artifacts through Ollama's native non-streaming `/api/chat` endpoint using only the Python standard library.

The backend identifier is:

```text
ollama
```

## Local-by-default does not mean network-impossible

The default API base is:

```text
http://localhost:11434
```

So the normal Ollama path targets the local machine and does not require an API key.

However, `--api-base` remains configurable. If a caller explicitly points PAIC at a remote Ollama-compatible service, the compiler will make a network request to that host. Do not describe the backend as cryptographically confined to localhost.

Official references:

- https://docs.ollama.com/api/introduction
- https://docs.ollama.com/api/chat
- https://docs.ollama.com/capabilities/thinking
- https://docs.ollama.com/api/authentication

## CLI

Local example:

```bash
paic compile conversation.clean.html \
  --backend ollama \
  --map-model <local-model> \
  --final-model <local-model> \
  --ollama-num-predict 4096 \
  -o migration
```

No API-key option is required for the default localhost path.

Optional explicit authenticated remote use:

```bash
export OLLAMA_API_KEY='...'
paic compile conversation.clean.html \
  --backend ollama \
  --api-base https://remote.example/ollama \
  --ollama-api-key-env OLLAMA_API_KEY \
  --map-model <model> \
  --final-model <model> \
  -o migration
```

The separate `--ollama-api-key-env` option is intentional. Ollama does **not** automatically reuse the global compiler `--api-key-env` setting or an existing `PAIC_API_KEY` value. This prevents a key intended for another provider from being sent to the default local service.

Only when `--ollama-api-key-env` is supplied does the factory resolve that environment variable and send:

```text
Authorization: Bearer <resolved key>
```

## Native API mapping

PAIC uses Ollama's native endpoint, not the OpenAI-compatibility shim.

Default request:

```text
POST http://localhost:11434/api/chat
Content-Type: application/json
```

Body shape:

```json
{
  "model": "<caller supplied model>",
  "messages": [
    {"role": "system", "content": "<PAIC system prompt>"},
    {"role": "user", "content": "<PAIC user prompt>"}
  ],
  "stream": false,
  "think": false,
  "options": {
    "num_predict": 4096,
    "temperature": 0.1
  }
}
```

`stream:false` keeps the compiler contract to one complete JSON response.

`think:false` requests no explicit reasoning trace for models that support disabling thinking. Some Ollama-supported models can treat thinking controls differently, so PAIC still ignores `message.thinking` unconditionally if the server returns it.

## Base normalization and validation

These base forms normalize to one `/api/chat` endpoint:

```text
http://localhost:11434
http://localhost:11434/api
https://remote.example/ollama
https://remote.example/ollama/api
```

The alpha backend requires:

- `http` or `https` scheme;
- a host/netloc;
- no embedded username/password;
- no query string or fragment;
- no traversal-style `.` / `..` path components;
- no backslash path syntax.

Unsafe base input is rejected with a generic error and is not echoed.

## Model identifiers

Unlike Gemini, the Ollama model identifier is sent in JSON rather than inserted into the request URL.

PAIC therefore avoids over-constraining current Ollama tag/namespace syntax. It accepts a bounded non-empty model name with no leading/trailing whitespace, whitespace/control characters, or DEL characters. Names such as these remain valid:

```text
qwen3:8b
namespace/model:tag
model@sha256:abc123
```

Invalid model input is not echoed in normal errors.

## `num_predict`

The backend maps:

```text
--ollama-num-predict 4096
```

to Ollama runtime option:

```json
{"num_predict": 4096}
```

The value must be a positive integer. It is a per-completion generation bound, not a statement about every model's context or output capacity.

If Ollama returns:

```text
done_reason = length
```

PAIC treats the completion as truncated and fails instead of persisting partial migration state.

## Response handling

A usable non-streaming response must contain:

```text
done = true
message.role = assistant
message.content = non-empty string
```

Current `done_reason` handling:

```text
stop    -> success
length  -> fail as num_predict truncation
missing -> compatibility success when done=true and final content is usable
empty   -> compatibility success when done=true and final content is usable
other   -> fail closed
```

The missing/empty compatibility path exists because documented older/non-streaming Ollama responses may omit `done_reason`. PAIC still requires `done:true`, assistant final text, and no tool-use result.

## Thinking and tools

Ollama thinking-capable models can return final answer text separately from reasoning in:

```text
message.content
message.thinking
```

PAIC only uses `message.content`. Returned thinking text is never copied into checkpoint notes or migration prompts.

If `message.thinking` is present it must be a string; malformed types fail the response-shape check.

The compiler does not execute tools. A non-empty `message.tool_calls` array therefore fails closed as an unexpected tool-use result rather than being silently ignored.

## Error and privacy boundary

Normal `CompilerError` text does not include:

- compiler system/user prompts;
- final or partial model output;
- thinking/reasoning text;
- tool call names/arguments;
- bearer-key values;
- unsafe model input;
- provider/base URL;
- raw HTTP response bodies;
- low-level transport exception detail.

Examples of safe categories:

```text
ollama backend HTTP status 500
ollama backend transport failed
ollama backend returned invalid JSON
unexpected Ollama response shape
ollama backend returned an incomplete response
ollama backend output reached num_predict
ollama backend returned an unexpected tool-use result
ollama backend returned an unsupported done reason
ollama backend returned no text content
```

Underlying Python exceptions remain chained where applicable for local debugging; the normal CLI prints only the safe compiler error.

## Validation boundary

CI uses deterministic mocked HTTP responses. It does not install Ollama, pull a model, start a daemon, or require network/model compute.

A real local smoke can be performed separately on a machine where Ollama and a model are already intentionally installed. Such a smoke is not required for package CI.

## Deliberate non-features

This alpha backend does not:

- install/start Ollama;
- pull or choose a model;
- stream responses;
- expose thinking traces;
- execute tools;
- send images;
- request structured output;
- use the OpenAI-compatible endpoint;
- automatically send `PAIC_API_KEY` or another provider key.

Those behaviors would expand either the local-system or security contract beyond the current plain-text compiler seam.
