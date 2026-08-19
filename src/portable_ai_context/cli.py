from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import sys

from . import __version__
from .adapters import load_conversation
from .checkpoint import MIN_BUDGET_TOKENS, build_extractive_checkpoint
from .compiler import (
    DEFAULT_ANTHROPIC_MAX_TOKENS,
    BackendConfig,
    compile_migration,
    create_backend,
)
from .conformance import inspect_conformance
from .errors import PortableAIContextError
from .exporters import write_bundle, write_standard
from .integrity import inspect as inspect_integrity
from .privacy import inspect_conversation


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _checkpoint_budget(value: str) -> int:
    parsed = _positive_int(value)
    if parsed < MIN_BUDGET_TOKENS:
        raise argparse.ArgumentTypeError(
            f"checkpoint budget must be at least {MIN_BUDGET_TOKENS} tokens"
        )
    return parsed


def _positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def cmd_inspect(args) -> int:
    conv = load_conversation(args.source)
    integrity = inspect_integrity(conv)
    privacy = inspect_conversation(conv)
    _print_json({
        "title": conv.title,
        "source": conv.source.kind,
        "message_count": len(conv.messages),
        "snapshot": {
            "updated_at": conv.snapshot.updated_at,
            "raw_node_count": conv.snapshot.raw_node_count,
        },
        "integrity": integrity.to_dict(),
        "privacy": privacy.to_dict(),
    })
    return 0


def cmd_verify(args) -> int:
    conv = load_conversation(args.source)
    report = inspect_integrity(conv)
    _print_json(report.to_dict())
    if args.show_tail:
        last_user = next((m for m in reversed(conv.messages) if m.role == "user"), None)
        last_assistant = next((m for m in reversed(conv.messages) if m.role == "assistant"), None)
        print("\nLAST USER:\n" + (last_user.text if last_user else "<none>"))
        print("\nLAST ASSISTANT:\n" + (last_assistant.text if last_assistant else "<none>"))
    return 0


def cmd_conform(args) -> int:
    """Run the shared canonical/round-trip contract without printing conversation text."""
    conv = load_conversation(args.source)
    report = inspect_conformance(conv)
    _print_json(report.to_dict())
    return 0 if report.ok else 3


def cmd_smoke(args) -> int:
    """Run a live capture smoke test without printing conversation content."""
    conv = load_conversation(args.source)
    report = inspect_integrity(conv)
    _print_json({
        "ok": True,
        "platform": platform.system().lower(),
        "source_kind": conv.source.kind,
        "capture_method": conv.source.metadata.get("capture_method"),
        "message_count": report.message_count,
        "snapshot_updated_at": report.snapshot_updated_at,
        "raw_node_count": report.raw_node_count,
        "conversation_digest": report.conversation_digest,
        "last_user_hash": report.last_user_hash,
        "last_assistant_hash": report.last_assistant_hash,
    })
    return 0


def cmd_extract(args) -> int:
    conv = load_conversation(args.source)
    paths = write_standard(conv, args.output)
    _print_json({name: str(path) for name, path in paths.items()})
    return 0


def cmd_bundle(args) -> int:
    conv = load_conversation(args.source)
    path = write_bundle(conv, args.output)
    print(path)
    return 0


def cmd_checkpoint(args) -> int:
    conv = load_conversation(args.source)
    try:
        result = build_extractive_checkpoint(
            conv,
            budget_tokens=args.budget,
            profile=args.profile,
            chars_per_token=args.chars_per_token,
        )
    except ValueError as exc:
        raise PortableAIContextError(str(exc)) from exc
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out / "CHECKPOINT.md"
    report_path = out / "checkpoint-report.json"
    checkpoint_path.write_text(result.markdown, encoding="utf-8")
    report_path.write_text(
        json.dumps(result.report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _print_json({
        "checkpoint": str(checkpoint_path),
        "report": str(report_path),
        "summary": result.report.to_dict(),
    })
    return 0


def cmd_compile(args) -> int:
    conv = load_conversation(args.source)
    backend = create_backend(
        args.backend,
        BackendConfig(
            api_base=args.api_base,
            api_key_env=args.api_key_env,
            timeout=args.timeout,
            environment=os.environ,
            options={"anthropic_max_tokens": args.anthropic_max_tokens},
        ),
    )
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    result = compile_migration(
        conv,
        backend=backend,
        map_model=args.map_model,
        final_model=args.final_model,
        chunk_chars=args.chunk_chars,
        reduce_chars=args.reduce_chars,
        state_path=args.state,
        budget_tokens=args.budget,
        profile=args.profile,
        chars_per_token=args.chars_per_token,
    )
    prompt_path = out / "MIGRATION_PROMPT.md"
    notes_path = out / "checkpoint.notes.md"
    report_path = out / "compile-report.json"
    prompt_path.write_text(result.final + "\n", encoding="utf-8")
    notes_path.write_text(
        "\n\n".join(f"# Note {i}\n\n{x}" for i, x in enumerate(result.notes, 1)) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(result.report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _print_json({
        "migration_prompt": str(prompt_path),
        "checkpoint_notes": str(notes_path),
        "compile_report": str(report_path),
        "budget": result.report.to_dict(),
    })
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="paic", description="Portable AI Context")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="inspect source, privacy, and integrity")
    inspect_p.add_argument("source")
    inspect_p.set_defaults(func=cmd_inspect)

    verify_p = sub.add_parser("verify", help="show deterministic integrity metadata")
    verify_p.add_argument("source")
    verify_p.add_argument("--show-tail", action="store_true")
    verify_p.set_defaults(func=cmd_verify)

    conform_p = sub.add_parser(
        "conform",
        help="run content-free canonical and standard round-trip checks",
    )
    conform_p.add_argument("source")
    conform_p.set_defaults(func=cmd_conform)

    smoke_p = sub.add_parser(
        "smoke",
        help="run a content-free live capture smoke test",
    )
    smoke_p.add_argument("source")
    smoke_p.set_defaults(func=cmd_smoke)

    extract_p = sub.add_parser("extract", help="write canonical clean artifacts")
    extract_p.add_argument("source")
    extract_p.add_argument("-o", "--output", required=True)
    extract_p.set_defaults(func=cmd_extract)

    bundle_p = sub.add_parser("bundle", help="write alpha .aicb bundle")
    bundle_p.add_argument("source")
    bundle_p.add_argument("-o", "--output", required=True)
    bundle_p.set_defaults(func=cmd_bundle)

    checkpoint_p = sub.add_parser(
        "checkpoint",
        help="build a deterministic no-AI extractive checkpoint",
    )
    checkpoint_p.add_argument("source")
    checkpoint_p.add_argument("-o", "--output", required=True)
    checkpoint_budget_group = checkpoint_p.add_mutually_exclusive_group()
    checkpoint_budget_group.add_argument(
        "--budget",
        type=_checkpoint_budget,
        help=f"target checkpoint token budget (minimum {MIN_BUDGET_TOKENS})",
    )
    checkpoint_budget_group.add_argument(
        "--profile",
        choices=["lite", "standard", "full"],
        help="named checkpoint budget profile; defaults to standard",
    )
    checkpoint_p.add_argument(
        "--chars-per-token",
        type=_positive_float,
        default=4.0,
        help="character/token estimate used by the dependency-free counter",
    )
    checkpoint_p.set_defaults(func=cmd_checkpoint)

    compile_p = sub.add_parser("compile", help="compile a continuation-focused migration prompt")
    compile_p.add_argument("source")
    compile_p.add_argument("-o", "--output", required=True)
    compile_p.add_argument(
        "--backend",
        default="openai-compatible",
        help="registered compiler backend identifier (default: openai-compatible)",
    )
    compile_p.add_argument(
        "--api-base",
        help="provider API base URL; required by openai-compatible, optional for anthropic",
    )
    compile_p.add_argument("--api-key-env", default="PAIC_API_KEY")
    compile_p.add_argument("--map-model", required=True)
    compile_p.add_argument("--final-model", required=True)
    compile_p.add_argument(
        "--anthropic-max-tokens",
        type=_positive_int,
        default=DEFAULT_ANTHROPIC_MAX_TOKENS,
        help=(
            "Anthropic Messages API max_tokens per completion "
            f"(default: {DEFAULT_ANTHROPIC_MAX_TOKENS})"
        ),
    )
    compile_p.add_argument("--chunk-chars", type=_positive_int, default=120000)
    compile_p.add_argument("--reduce-chars", type=_positive_int, default=180000)
    budget_group = compile_p.add_mutually_exclusive_group()
    budget_group.add_argument("--budget", type=_positive_int, help="target final migration-prompt token budget")
    budget_group.add_argument(
        "--profile",
        choices=["lite", "standard", "full"],
        help="named final migration-prompt budget profile",
    )
    compile_p.add_argument(
        "--chars-per-token",
        type=_positive_float,
        default=4.0,
        help="character/token estimate used by the dependency-free fallback counter",
    )
    compile_p.add_argument("--state")
    compile_p.add_argument("--timeout", type=_positive_int, default=300)
    compile_p.set_defaults(func=cmd_compile)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PortableAIContextError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
