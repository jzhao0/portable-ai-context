# Architecture

```text
Source
  |
  v
Adapter  --->  Canonical Conversation
                  |        |
                  |        +--> Privacy inspection
                  |        +--> Integrity verification
                  |
                  +--> Exporters --> clean HTML / TXT / JSONL / .aicb
                  |
                  +--> Compiler  --> checkpoint notes --> migration prompt
```

## Boundaries

### Adapter

Source-specific parsing belongs here. ChatGPT React-stream knowledge must not leak into compiler code.

### Canonical model

The rest of the system should not care whether a message came from ChatGPT, Claude, a JSONL file, or a future browser extension.

### Privacy

Privacy inspection is a separate concern. Runtime metadata exclusion happens during parsing; conversation-body secret detection happens after canonicalization.

### Integrity

Integrity is deterministic and model-free. It is designed to answer: *what exactly did we capture?*

### Compiler

Compilation is optional. It converts a potentially huge canonical conversation into a continuation-focused state prompt through map/reduce/final stages. Backends are replaceable.
