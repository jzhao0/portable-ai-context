# Migration token budgets

Portable AI Context can target an explicit final migration-prompt token budget while keeping the existing character-based map/reduce chunk controls available.

## Named profiles

The alpha profiles are output targets for `MIGRATION_PROMPT.md`; they are **not** claims about any model's maximum context window.

| Profile | Target final prompt budget |
| --- | ---: |
| `lite` | 4,000 tokens |
| `standard` | 16,000 tokens |
| `full` | 64,000 tokens |

Examples:

```bash
paic compile conversation.clean.html \
  --api-base https://api.example.com/v1 \
  --map-model fast-model \
  --final-model strong-model \
  --profile standard \
  -o migration
```

Or set an explicit target:

```bash
paic compile conversation.clean.html \
  --api-base https://api.example.com/v1 \
  --map-model fast-model \
  --final-model strong-model \
  --budget 12000 \
  -o migration
```

`--budget` and `--profile` are mutually exclusive.

## Token counter abstraction

The compiler operates against a small `TokenCounter` interface with:

- `count(text) -> int`;
- a counter name;
- an `exact` flag indicating whether the count is exact for its intended tokenizer/request-count contract or an estimate.

### Dependency-free default

The base package still has no runtime dependencies. The default CLI counter is `CharacterTokenCounter`, which estimates tokens from character count. Its default is 4 characters per token and can be changed with `--chars-per-token`.

```text
--token-counter character
```

This estimate is intentionally model-agnostic and must not be presented as an exact count for a named model.

### Optional local tiktoken counter

Install the optional tokenizer extra when you want exact raw-text counting under an OpenAI tiktoken encoding:

```bash
pip install 'portable-ai-context[tokenizers]'
```

Then select:

```bash
paic compile conversation.clean.html \
  --api-base https://api.example.com/v1 \
  --map-model fast-model \
  --final-model gpt-5 \
  --token-counter tiktoken \
  --profile standard \
  -o migration
```

With no additional tokenizer option, PAIC passes `--final-model` to tiktoken's own `encoding_for_model()` lookup. PAIC does not maintain a duplicate model-to-encoding table and does not guess when tiktoken does not recognize a model.

You can supply a separate lookup model:

```text
--tokenizer-model <model>
```

Or bypass model lookup with an explicit encoding:

```text
--tiktoken-encoding o200k_base
```

Explicit encoding wins over model lookup.

If the optional dependency is absent, PAIC returns a concise install hint rather than making every base installation depend on tiktoken.

## What `tokenizer_exact=true` means for tiktoken

For `TiktokenTokenCounter`, `exact=true` has a deliberately narrow definition:

> The count is exact for the plain text passed to `count()` under the resolved tiktoken encoding.

It does **not** claim exact billing/request counts for an entire OpenAI Responses/Chat request. Provider request framing, roles, tools, images/audio, cached input, reasoning, and provider-added tokens are outside this raw-text counter.

The counter uses tiktoken's ordinary-text encoding path. Text that merely looks like special-token syntax is treated as ordinary user text rather than privileged tokenizer control syntax.

`tiktoken` is an optional external tokenizer package. Depending on its own cache state/version, initializing an encoding may require tiktoken to populate its tokenizer data cache; PAIC does not vendor or silently invent encoding tables.

## Opt-in provider-native input counting

For the built-in Anthropic and Gemini compiler backends, PAIC can instead ask the selected provider to count each text value as **one user-role input using `--final-model`**:

```text
--token-counter provider-native
```

This mode is available only with:

```text
--backend anthropic
--backend gemini
```

It deliberately reuses the already-created compiler backend, including the same API key, API base, timeout, and provider headers. There is no second token-counter credential path.

### Anthropic

PAIC calls:

```text
POST /v1/messages/count_tokens
```

with the selected final model and one user message containing the text being counted.

The compile report uses a name such as:

```text
anthropic_count_tokens:claude-sonnet-...
```

and reports:

```text
tokenizer_exact = false
```

This is intentional. Anthropic documents its token-count result as an **estimate** that can differ slightly from actual message input usage and can include automatically added provider tokens. PAIC does not relabel that estimate as exact.

### Gemini

PAIC calls the selected model's:

```text
models/...:countTokens
```

with one user `Content` containing the text being counted.

The compile report uses a name such as:

```text
gemini_count_tokens:gemini-...
```

and reports:

```text
tokenizer_exact = true
```

Here `exact=true` has a narrow provider-request meaning:

> The value is the Gemini `countTokens` result for that selected model and one-user-content request shape at call time.

It is not a bundled/offline tokenizer guarantee and is not a claim about output, thinking, cached, tool, image, audio, video, or billing-token totals.

### Network and privacy boundary

`provider-native` is **not** a local tokenizer. Each `count(text)` call sends that text to the configured provider count endpoint.

During a normal compile, PAIC counts at least:

1. the full rendered source conversation for the source count;
2. the generated final migration prompt for the output count;
3. the reduced final prompt as an additional count if a budget-reduction pass occurs.

This matters with `--state`: even when incremental compilation can avoid regenerating map notes for unchanged old messages, provider-native source counting still sends the full rendered source text to the count endpoint. Choose this mode only when that network disclosure is acceptable.

The default `character` mode and optional `tiktoken` mode do not gain this provider-count network behavior.

Custom `--api-base` values retain the same trust boundary as the matching compiler backend: the configured endpoint receives the API credential and the counted text.

### Compatibility rules

`--tokenizer-model` and `--tiktoken-encoding` remain tiktoken-only. PAIC rejects them when `provider-native` is selected rather than silently mixing two counting contracts.

Provider-native counting is not added to `paic checkpoint`; deterministic checkpoint mode remains offline/no-AI.

PAIC does not currently invent native count-only adapters for OpenAI-compatible endpoints or Ollama. Those ecosystems do not provide one sufficiently uniform count-only contract through the interfaces PAIC currently targets.

## Why PAIC does not claim universal offline exact counting

Compiler providers do not expose the same token-count contract:

- OpenAI publishes tiktoken for supported encodings/model mappings.
- Anthropic exposes `/v1/messages/count_tokens`, but its documentation describes the returned count as an estimate and notes that automatically added system tokens may be included.
- Gemini exposes model-native `models.countTokens`, which is a provider API operation rather than a bundled offline tokenizer.
- Ollama exposes actual `prompt_eval_count` / `eval_count` usage on model execution responses, but the native API does not provide one universal count-only tokenizer endpoint for every local model.

The network counters therefore remain distinct from local raw-text tokenizers even though both satisfy PAIC's small `TokenCounter` interface.

## Python API

Library callers can continue injecting any exact or estimated counter without changing the compiler pipeline:

```python
from portable_ai_context.compiler import CallableTokenCounter, compile_migration

counter = CallableTokenCounter(
    fn=my_exact_token_count,
    name="my-model-tokenizer",
    exact=True,
)

result = compile_migration(
    conversation,
    backend=backend,
    map_model="fast-model",
    final_model="strong-model",
    budget_tokens=12000,
    token_counter=counter,
)
```

The optional tiktoken implementation is also public:

```python
from portable_ai_context.compiler import TiktokenTokenCounter

counter = TiktokenTokenCounter(encoding_name="o200k_base")
```

Provider-native counting can be constructed around a supported built-in backend:

```python
from portable_ai_context.compiler import ProviderNativeTokenCounter

counter = ProviderNativeTokenCounter(
    backend=backend,
    model="gemini-...",
)
```

The backend must expose PAIC's reviewed Anthropic or Gemini native count contract.

## Continuation priority under pressure

When a budget is configured, the final compiler is told to preserve continuation-critical state before background detail. If the first final prompt exceeds the configured budget, the compiler performs one additional budget-reduction pass with this priority:

1. current breakpoint, unresolved work, blockers, and exact next action;
2. verified current environment/state, versions, paths, commits, measurements, and test evidence;
3. user constraints, security/privacy rules, decisions, and rationale needed to continue correctly;
4. completed work that prevents costly or dangerous repetition;
5. older background and chronology only when budget remains.

The compiler does **not** silently slice the generated prompt at an arbitrary token/character boundary. If the model still exceeds the target after the reduction pass, the overrun is reported explicitly.

## Compile report

Every compile writes `compile-report.json`. It includes:

- `tokenizer`;
- `tokenizer_exact`;
- selected `profile` and `budget_tokens`;
- `source_token_estimate`;
- `output_token_estimate`;
- `compression_ratio` (output tokens divided by source tokens; lower means more compression);
- `budget_overrun_tokens`;
- `budget_met`;
- whether `budget_reduction_applied`.

The field names use `estimate` even when a counter is exact so report consumers can use one stable schema; `tokenizer_exact` distinguishes the selected counter's declared semantics.

For provider-native mode, remember that `source_token_estimate` and `output_token_estimate` are one-user-input request counts, not local raw-text lengths.

## Character fallback compatibility

`--chunk-chars` and `--reduce-chars` remain available and retain their original map/reduce behavior. If neither `--budget` nor `--profile` is supplied, compilation does not add a token-budget reduction stage. The compile report still provides source/output counts using the selected counter.
