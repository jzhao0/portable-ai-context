from __future__ import annotations

import argparse
import importlib.metadata
import json
from typing import Any

import portable_ai_context
import portable_ai_context.compiler as compiler_api
from portable_ai_context.cli import build_parser


INVENTORY_SCHEMA = "paic-public-surface-inventory-1"
DISTRIBUTION_NAME = "portable-ai-context"


def _json_safe_default(value: Any) -> Any:
    if value is argparse.SUPPRESS:
        return "<suppressed>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)) and all(
        item is None or isinstance(item, (str, int, float, bool)) for item in value
    ):
        return list(value)
    return "<nonsemantic-default>"


def _type_name(action: argparse.Action) -> str | None:
    value = getattr(action, "type", None)
    if value is None:
        return None
    name = getattr(value, "__name__", None)
    if isinstance(name, str) and name:
        return name
    return type(value).__name__


def _action_kind(action: argparse.Action) -> str:
    if isinstance(action, argparse._StoreTrueAction):
        return "store_true"
    if isinstance(action, argparse._StoreFalseAction):
        return "store_false"
    if isinstance(action, argparse._StoreConstAction):
        return "store_const"
    if isinstance(action, argparse._AppendAction):
        return "append"
    if isinstance(action, argparse._AppendConstAction):
        return "append_const"
    if isinstance(action, argparse._CountAction):
        return "count"
    if isinstance(action, argparse._VersionAction):
        return "version"
    if isinstance(action, argparse._StoreAction):
        return "store"
    return action.__class__.__name__


def _choices(action: argparse.Action) -> list[Any] | None:
    value = getattr(action, "choices", None)
    if value is None:
        return None
    items = list(value)
    if not all(item is None or isinstance(item, (str, int, float, bool)) for item in items):
        return ["<nonsemantic-choice-set>"]
    return items


def _argument_record(action: argparse.Action) -> dict[str, Any]:
    return {
        "dest": action.dest,
        "kind": _action_kind(action),
        "nargs": action.nargs,
        "required": bool(getattr(action, "required", False)),
        "type": _type_name(action),
        "choices": _choices(action),
        "default": _json_safe_default(action.default),
    }


def _parser_surface(parser: argparse.ArgumentParser) -> dict[str, Any]:
    positionals: list[dict[str, Any]] = []
    options: list[dict[str, Any]] = []

    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if isinstance(action, argparse._SubParsersAction):
            continue
        record = _argument_record(action)
        if action.option_strings:
            record["option_strings"] = sorted(action.option_strings)
            options.append(record)
        else:
            positionals.append(record)

    options.sort(key=lambda record: (record["dest"], record["option_strings"]))
    positionals.sort(key=lambda record: record["dest"])
    return {
        "positionals": positionals,
        "options": options,
    }


def _cli_surface() -> dict[str, Any]:
    parser = build_parser()
    subparsers_action: argparse._SubParsersAction | None = None
    version_options: list[str] = []

    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparsers_action = action
        elif isinstance(action, argparse._VersionAction):
            version_options.extend(action.option_strings)

    if subparsers_action is None:
        raise RuntimeError("paic CLI has no subcommand registry")

    commands = {
        name: _parser_surface(subparser)
        for name, subparser in sorted(subparsers_action.choices.items())
    }
    return {
        "program": parser.prog,
        "version_option_strings": sorted(version_options),
        "subcommands": commands,
    }


def _package_surface() -> dict[str, Any]:
    try:
        distribution = importlib.metadata.distribution(DISTRIBUTION_NAME)
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            "portable-ai-context distribution metadata is unavailable; install the package before generating the inventory"
        ) from exc

    console_scripts = {
        entry.name: entry.value
        for entry in distribution.entry_points
        if entry.group == "console_scripts"
    }
    extras = sorted(distribution.metadata.get_all("Provides-Extra") or [])
    return {
        "distribution_name": distribution.metadata["Name"],
        "requires_python": distribution.metadata.get("Requires-Python"),
        "optional_extras": extras,
        "console_scripts": dict(sorted(console_scripts.items())),
    }


def build_inventory() -> dict[str, Any]:
    return {
        "inventory_schema": INVENTORY_SCHEMA,
        "package": _package_surface(),
        "python_api": {
            "portable_ai_context": sorted(portable_ai_context.__all__),
            "portable_ai_context.compiler": sorted(compiler_api.__all__),
        },
        "cli": _cli_surface(),
    }


def main() -> int:
    print(json.dumps(build_inventory(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
