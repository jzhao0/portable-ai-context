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

The dependency-free CLI fallback is `CharacterTokenCounter`, which estimates tokens from character count. Its default is 4 characters per token and can be changed with `--chars-per-token`.

This estimate is intentionally model-agnostic. It should not be presented as an exact count for a named model.

Library callers can inject an exact tokenizer without changing the compiler pipeline:

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

No paid API call or tokenizer package is required by the core or CI tests.

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

The field names use `estimate` even when an injected counter is exact so report consumers can use one stable schema; `tokenizer_exact` distinguishes exact from estimated counts.

## Character fallback compatibility

`--chunk-chars` and `--reduce-chars` remain available and retain their original map/reduce behavior. If neither `--budget` nor `--profile` is supplied, compilation does not add a token-budget reduction stage. The compile report still provides dependency-free source/output token estimates for observability.
