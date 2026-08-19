# Compiler backend extension contract

Portable AI Context separates **migration compilation policy** from **provider transport**.

The core pipeline consumes the structural `CompilerBackend` protocol:

```python
class CompilerBackend(Protocol):
    def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        stage: str,
    ) -> str: ...
```

The pipeline does not need to know whether a completion came from an OpenAI-compatible endpoint, Anthropic, a future Gemini/Ollama transport, or a deterministic test backend.

The alpha registry/factory layer lets the CLI choose and construct provider transports without modifying `compile_migration()`.

## Built-in backends

Current built-ins are:

```text
openai-compatible  (default)
anthropic
```

The OpenAI-compatible path remains the default for backward compatibility:

```bash
paic compile conversation.clean.html \
  --api-base https://api.example.com/v1 \
  --map-model fast-model \
  --final-model strong-model \
  -o migration
```

Explicit OpenAI-compatible selection:

```bash
paic compile conversation.clean.html \
  --backend openai-compatible \
  --api-base https://api.example.com/v1 \
  --map-model fast-model \
  --final-model strong-model \
  -o migration
```

Anthropic selection:

```bash
paic compile conversation.clean.html \
  --backend anthropic \
  --api-key-env ANTHROPIC_API_KEY \
  --map-model <map-model> \
  --final-model <final-model> \
  --anthropic-max-tokens 4096 \
  -o migration
```

See [`anthropic-backend.md`](anthropic-backend.md) for the Messages API mapping and stop/error contract.

`--api-base`, `--api-key-env`, and `--timeout` remain shared compiler-construction inputs. Provider-specific validation belongs to the selected backend factory rather than the compiler pipeline.

## Python registry API

The alpha exports:

```python
from portable_ai_context.compiler import (
    BackendConfig,
    available_backends,
    create_backend,
    register_backend,
)
```

The registry uses safe lowercase identifiers such as:

```text
openai-compatible
anthropic
future-provider
local_model
```

Unsafe names are rejected. Duplicate names are rejected rather than silently replaced.

A backend factory receives a `BackendConfig` and returns an object satisfying the `CompilerBackend` protocol. Registry construction also verifies that the returned object exposes a callable `complete` method, so an invalid factory result fails at the construction seam rather than later inside the migration pipeline.

Conceptually:

```python
def build_provider(config: BackendConfig) -> CompilerBackend:
    ...

register_backend("provider-name", build_provider)
backend = create_backend("provider-name", config)
```

`BackendConfig.environment` and `BackendConfig.options` are excluded from the dataclass representation. This reduces the chance that normal debugging accidentally expands environment secrets or future provider options.

Built-in factories resolve API keys from a configured environment-variable **name**. Key values are not stored directly in `BackendConfig`.

## Adding another built-in provider

A future Gemini/Ollama implementation should follow the same separation already used by Anthropic:

1. implement a backend object with `complete(model, system, user, stage)`;
2. implement a small factory that validates/resolves its construction inputs;
3. register a safe backend identifier;
4. add provider-specific tests and, where needed, provider-specific CLI configuration surface;
5. leave `compile_migration()` unchanged unless the provider exposes a genuinely new compiler-semantic capability rather than a transport difference.

The `stage` value lets a backend observe which compiler phase is executing:

```text
map
merge
final
budget
```

A backend may use that metadata for logging/routing, but it must still return plain completion text to the pipeline.

## Error and privacy contract

Normal compiler errors must be safe to show to the user.

Built-in remote transports therefore do **not** include these values in `CompilerError` text:

- API-key values;
- system/user prompts;
- source chunks;
- final migration content;
- raw provider response bodies;
- raw transport error details;
- provider URLs.

The original exception is preserved through Python exception chaining where applicable, but the normal PAIC CLI prints only the safe `CompilerError` message.

Backend construction follows the same rule. Unexpected factory exceptions are wrapped as:

```text
compiler backend construction failed
```

Factories that return an object without callable `complete` fail as:

```text
compiler backend factory returned an invalid backend
```

Unknown backend input is not echoed. The user-facing error lists only safe registered backend identifiers.

## Compatibility and stability

This registry is an **alpha extension seam**, not a 1.0 plugin ABI promise.

Current non-goals:

- no Python package entry-point discovery;
- no third-party automatic plugin loading;
- no Gemini/Ollama transport yet;
- no change to map/reduce/final/budget prompt semantics.

Python callers can continue bypassing the registry entirely and inject any compatible backend directly:

```python
result = compile_migration(
    conversation,
    backend=my_backend,
    map_model="map-model",
    final_model="final-model",
)
```

That direct protocol-based API remains the narrowest testing and integration boundary.
