from __future__ import annotations

import argparse
import json
import os
import platform
from pathlib import Path
import sys

from .adapters import load_conversation
from .compiler import OpenAICompatibleBackend, compile_migration
from .errors import PortableAIContextError
from .exporters import write_bundle, write_standard
from .integrity import inspect as inspect_integrity
from .privacy import inspect_conversation


def _print_json(value) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


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


def cmd_smoke(args) -> int:
    """Run a live capture smoke test without printing conversation content."""
    conv = load_conversation(args.source)
    report = inspect_integrity(conv)
    _print_json({
        "ok": True,
        "platform": platform.system().lower(),
        "source_kind": conv.source.kind,
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


def cmd_compile(args) -> int:
    conv = load_conversation(args.source)
    key = os.environ.get(args.api_key_env)
    if not key:
        raise PortableAIContextError(
            f"environment variable {args.api_key_env!r} is not set"
        )
    backend = OpenAICompatibleBackend(api_base=args.api_base, api_key=key, timeout=args.timeout)
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    final, notes = compile_migration(
        conv,
        backend=backend,
        map_model=args.map_model,
        final_model=args.final_model,
        chunk_chars=args.chunk_chars,
        reduce_chars=args.reduce_chars,
        state_path=args.state,
    )
    (out / "MIGRATION_PROMPT.md").write_text(final + "\n", encoding="utf-8")
    (out / "checkpoint.notes.md").write_text(
        "\n\n".join(f"# Note {i}\n\n{x}" for i, x in enumerate(notes, 1)) + "\n",
        encoding="utf-8",
    )
    print(out / "MIGRATION_PROMPT.md")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="paic", description="Portable AI Context")
    sub = p.add_subparsers(dest="command", required=True)

    inspect_p = sub.add_parser("inspect", help="inspect source, privacy, and integrity")
    inspect_p.add_argument("source")
    inspect_p.set_defaults(func=cmd_inspect)

    verify_p = sub.add_parser("verify", help="show deterministic integrity metadata")
    verify_p.add_argument("source")
    verify_p.add_argument("--show-tail", action="store_true")
    verify_p.set_defaults(func=cmd_verify)

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

    compile_p = sub.add_parser("compile", help="compile a continuation-focused migration prompt")
    compile_p.add_argument("source")
    compile_p.add_argument("-o", "--output", required=True)
    compile_p.add_argument("--api-base", required=True)
    compile_p.add_argument("--api-key-env", default="PAIC_API_KEY")
    compile_p.add_argument("--map-model", required=True)
    compile_p.add_argument("--final-model", required=True)
    compile_p.add_argument("--chunk-chars", type=int, default=120000)
    compile_p.add_argument("--reduce-chars", type=int, default=180000)
    compile_p.add_argument("--state")
    compile_p.add_argument("--timeout", type=int, default=300)
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
