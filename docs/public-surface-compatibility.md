# Pre-v1 public Python / CLI surface inventory

Tracking issue: #85

Portable AI Context already exposes a user-facing alpha surface through its installed package, Python exports, and `paic` command line. This document makes changes to that surface **reviewable** before v1. It does not declare the current alpha API stable or promise that every listed name/option will remain forever.

## Why an inventory exists

Behavioral tests can miss a public-surface regression. For example, a refactor can rename a CLI option, remove a Python export, change a choice/default, or drop a console entry point while unrelated functional tests still pass.

PAIC therefore commits a semantic snapshot of the current installed alpha surface:

```text
tests/fixtures/public_surface_0_1_alpha.json
```

CI regenerates the same semantic structure from the installed distribution and current parser/module exports, then requires exact object equality with the committed fixture.

A change before v1 remains permitted. The inventory does not block intentional evolution; it makes the change appear as an explicit reviewed fixture diff instead of silent drift.

## Inventory generator

The deterministic generator is:

```text
tools/public_surface_inventory.py
```

It requires an installed `portable-ai-context` distribution because package metadata is read through `importlib.metadata`. Normal CI installs the repository in editable mode before running tests, so the inventory sees the metadata a Python installation exposes rather than separately re-parsing `pyproject.toml` with another implementation.

The current inventory schema identifier is internal to the snapshot tool:

```text
paic-public-surface-inventory-1
```

This is **not** a PAIC canonical conversation schema version and is not a public compatibility promise by itself.

## Package surface recorded

The inventory records:

- installed distribution name;
- `Requires-Python` metadata;
- optional extra names;
- installed `console_scripts` entry points.

For the current alpha this includes:

```text
distribution: portable-ai-context
requires-python: >=3.10
extras: mcp, tokenizers
console script: paic = portable_ai_context.cli:main
```

The inventory does not record dependency resolver state, local installation paths, wheel filenames, virtual-environment paths, or environment variable values.

## Python API surface recorded

The inventory records the sorted explicit `__all__` values from:

```text
portable_ai_context
portable_ai_context.compiler
```

Only names intentionally exported through those module-level lists are included. Private/internal modules, helper functions, implementation classes not exported in `__all__`, and incidental importability are not promoted into a compatibility promise by the inventory.

If a name is intentionally added/removed/renamed before v1, update the fixture in the same reviewed change and document the user-facing consequence when material.

## CLI surface recorded

The inventory records semantic argparse structure, not rendered help text.

Recorded:

- program name;
- top-level version option strings;
- subcommand names;
- positional argument destination names;
- option strings grouped by one semantic argument;
- normalized action kind (`store`, `store_true`, etc.);
- `nargs`;
- `required` flag;
- safe argument type-function name;
- scalar/list choices;
- JSON-safe semantic defaults.

Not recorded:

- `--help` output formatting;
- help/description/epilog wording;
- line wrapping/terminal width;
- argparse-generated usage text;
- localized/error wording;
- callable reprs or memory addresses;
- command implementation function objects.

This keeps the fixture stable across supported Python versions while still detecting user-visible command/argument changes.

## Environment and secret boundary

The inventory may record the **name** of a default API-key environment variable when that name is itself a documented CLI default, for example `PAIC_API_KEY`.

It never reads or serializes the value of that environment variable. It does not capture:

- `os.environ` contents;
- API keys/tokens;
- provider responses;
- filesystem paths;
- account/session state;
- browser state;
- live backend/adapter availability.

## What an inventory mismatch means

A mismatch is not automatically a defect. It means the public alpha surface changed and the change requires explicit review.

When intentional:

1. verify the behavior change is desired;
2. update implementation/tests/docs as appropriate;
3. regenerate/review the semantic inventory;
4. update the pinned fixture SHA in the same change;
5. describe breaking or materially additive user-facing changes in release notes.

Do not update the fixture/hash merely to make an unexplained CI failure disappear.

When unintentional, restore the prior surface instead of accepting the drift.

## Fixed fixture bytes

The fixture uses LF line endings on every checkout through `.gitattributes` so its raw bytes are stable on Windows/macOS/Linux.

Pinned SHA256:

```text
7d38a019a6bd850cc9c97d5e5600bb44aa24fcf8fe6e2605d80a2163173377bb
```

The pinned raw hash detects accidental fixture replacement/line-ending conversion; semantic equality is checked separately against a freshly generated inventory.

## Relationship to stable compatibility policy

This inventory is a **pre-v1 evidence mechanism**, not the final policy.

It does not decide:

- which alpha APIs v1 must preserve;
- semantic-versioning guarantees after v1;
- deprecation duration;
- whether additive CLI/API changes require minor versions;
- support duration for old flags/names;
- stable provider/backend behavior;
- stable canonical/bundle schemas.

Those decisions belong to the eventual v1 backward-compatibility policy.

The Roadmap item remains unchecked until that policy is intentionally defined. The inventory gives that future decision a concrete record of the public alpha surface that existed before stabilization.
