# Gemini generateContent compiler backend

Portable AI Context can compile migration artifacts through Google Gemini's REST `models.generateContent` endpoint using only the Python standard library.

The backend identifier is:

```text
gemini
```

## Why `generateContent` instead of Interactions

Google's current Gemini API reference recommends the newer Interactions API as the broader primitive for agentic workflows, server-side state, and complex multi-turn interaction. The same official reference still exposes `generateContent` as the standard REST content-generation endpoint and describes it as suitable for non-interactive tasks that wait for a complete response.

PAIC compiler calls are deliberately narrower:

- one compiler system prompt;
- one compiler user prompt;
- one non-streaming response;
- no provider-side conversation state;
- no tools or agent loop.

For that reason this alpha backend uses `models.generateContent` instead of introducing Interactions state into the compiler abstraction.

Official references:

- https://ai.google.dev/api
- https://ai.google.dev/api/generate-content

## CLI

Example shape:

```bash
paic compile conversation.clean.html \
  --backend gemini \
  --api-key-env GEMINI_API_KEY \
  --map-model <map-model> \
  --final-model <final-model> \
  --gemini-max-output-tokens 4096 \
  -o migration
```

PAIC does not hardcode a Gemini model ID. Callers provide map and final models explicitly.

If `--api-base` is omitted for Gemini, PAIC uses:

```text
https://generativelanguage.googleapis.com/v1beta
```

A compatible custom base can be supplied explicitly.

The global `--api-key-env` option remains unchanged for compiler-backend compatibility. To use Google's conventional environment variable, pass:

```text
--api-key-env GEMINI_API_KEY
```

## REST mapping

For a compiler completion PAIC sends:

```text
POST /v1beta/models/<model>:generateContent
Content-Type: application/json
x-goog-api-key: <resolved key>
```

The request body is equivalent to:

```json
{
  "systemInstruction": {
    "parts": [{"text": "<compiler system prompt>"}]
  },
  "contents": [
    {
      "role": "user",
      "parts": [{"text": "<compiler user prompt>"}]
    }
  ],
  "generationConfig": {
    "candidateCount": 1,
    "maxOutputTokens": 4096,
    "temperature": 0.1,
    "responseMimeType": "text/plain"
  }
}
```

No tools, grounding, search, streaming, structured output, media, caching, or thought-summary option is enabled.

## Model-path validation

Gemini's model identifier becomes part of the request URL, so the backend validates it before constructing the endpoint.

Accepted shape is a bounded safe leaf optionally prefixed with exactly one `models/`:

```text
gemini-...
models/gemini-...
```

Path traversal, query strings, fragments, extra slashes, and unsafe model input are rejected with a generic error that does not echo the supplied value.

## `maxOutputTokens`

The Gemini API exposes `generationConfig.maxOutputTokens`; the model-specific maximum varies by model.

PAIC therefore uses a conservative per-completion default:

```text
--gemini-max-output-tokens 4096
```

Callers can override this with a positive integer. PAIC does not claim that 4096 is a provider-wide maximum.

If a candidate returns:

```text
finishReason = MAX_TOKENS
```

PAIC fails the completion instead of silently preserving truncated migration state.

## Response handling

The alpha compiler asks for one candidate and requires exactly one usable candidate.

Successful output requires:

```text
finishReason = STOP
```

PAIC reads `candidate.content.parts` in order and joins only string `text` parts that are not marked:

```json
{"thought": true}
```

Thought-summary text is deliberately excluded. `thoughtSignature`, function/tool payloads, media data, and other non-text fields are not converted into migration content.

This matters because thinking-capable Gemini models can attach thought-related metadata to response parts. PAIC's compiler output remains final answer text only.

## Fail-closed finish reasons

The backend fails closed for the currently documented non-success outcomes, including:

```text
MAX_TOKENS
SAFETY
RECITATION
LANGUAGE
OTHER
BLOCKLIST
PROHIBITED_CONTENT
SPII
MALFORMED_FUNCTION_CALL
IMAGE_SAFETY
IMAGE_PROHIBITED_CONTENT
IMAGE_OTHER
NO_IMAGE
IMAGE_RECITATION
UNEXPECTED_TOOL_CALL
TOO_MANY_TOOL_CALLS
MISSING_THOUGHT_SIGNATURE
MALFORMED_RESPONSE
ESCALATION
FINISH_REASON_UNSPECIFIED
```

Unknown future finish reasons also fail closed and are not echoed into the normal error message.

If the API returns no candidates and `promptFeedback.blockReason` is present, PAIC reports only a generic prompt-blocked error. It does not print the provider's block reason, block message, safety ratings, or raw response body.

## Error and privacy boundary

Normal `CompilerError` text does not include:

- API-key values;
- unsafe model input;
- provider URL;
- compiler system/user prompts;
- raw HTTP response bodies;
- prompt feedback details;
- candidate `finishMessage` or safety ratings;
- thought text or signatures;
- low-level transport exception detail.

User-facing categories are concise, for example:

```text
gemini backend HTTP status 429
gemini backend transport failed
gemini backend returned invalid JSON
unexpected Gemini response shape
gemini backend prompt was blocked
gemini backend output reached maxOutputTokens
gemini backend candidate was blocked
gemini backend returned a non-text or incomplete result
gemini backend returned an unsupported finish reason
gemini backend returned no text content
```

Underlying Python exceptions are chained where applicable for local debugging, but the normal CLI prints only the safe compiler error.

## Validation boundary

CI uses deterministic mocked HTTP responses and the full cross-platform matrix. It does not require or spend a live Gemini API key.

A real paid API smoke remains a separate explicitly authorized validation activity.

## Deliberate non-features

This alpha backend does not enable:

- Interactions server-side state;
- streaming;
- tools/function calling;
- Google Search/grounding;
- code execution;
- prompt/context caching;
- images/audio/video/PDF input or output;
- structured JSON output;
- thought summaries;
- model auto-selection.

Those capabilities would expand the compiler/provider contract beyond the current plain-text completion seam.
