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
- an `exact` flag indicating whether the count is exact for its intended tokenizer or an estimate.

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

## What `tokenizer_exact=true` means

For `TiktokenTokenCounter`, `exact=true` has a deliberately narrow definition:

> The count is exact for the plain text passed to `count()` under the resolved tiktoken encoding.

It does **not** claim exact billing/request counts for an entire OpenAI Responses/Chat request. Provider request framing, roles, tools, images/audio, cached input, reasoning, and provider-added tokens are outside this raw-text counter.

The counter uses tiktoken's ordinary-text encoding path. Text that merely looks like special-token syntax is treated as ordinary user text rather than privileged tokenizer control syntax.

`tiktoken` is an optional external tokenizer package. Depending on its own cache state/version, initializing an encoding may require tiktoken to populate its tokenizer data cache; PAIC does not vendor or silently invent encoding tables.

## Why PAIC does not claim universal offline exact counting

Compiler providers do not expose the same token-count contract:

- OpenAI publishes tiktoken for supported encodings/model mappings.
- Anthropic exposes `/v1/messages/count_tokens`, but its documentation describes the returned count as an estimate and notes that automatically added system tokens may be included.
- Gemini exposes model-native `models.countTokens`, which is a provider API operation rather than a bundled offline tokenizer.
- Ollama exposes actual `prompt_eval_count` / `eval_count` usage on model execution responses, but the native API does not provide one universal count-only tokenizer endpoint for every local model.

Provider-native/network counters can therefore be added separately without mislabeling them as the same kind of local exact tokenizer.

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

The field names use `estimate` even when a counter is exact so report consumers can use one stable schema; `tokenizer_exact` distinguishes exact raw-text tokenizer counts from estimated counts.

## Character fallback compatibility

`--chunk-chars` and `--reduce-chars` remain available and retain their original map/reduce behavior. If neither `--budget` nor `--profile` is supplied, compilation does not add a token-budget reduction stage. The compile report still provides source/output counts using the selected counter.
