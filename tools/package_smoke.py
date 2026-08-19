from __future__ import annotations

import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def _run_json(command: list[str], *, check: bool = True) -> tuple[subprocess.CompletedProcess[str], dict]:
    run = subprocess.run(command, check=check, capture_output=True, text=True)
    return run, json.loads(run.stdout)


def main() -> int:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    expected_version = project["version"]
    installed_version = importlib.metadata.version("portable-ai-context")
    if installed_version != expected_version:
        raise SystemExit(
            f"distribution version mismatch: installed={installed_version!r} expected={expected_version!r}"
        )

    import portable_ai_context

    if portable_ai_context.__version__ != expected_version:
        raise SystemExit(
            "package __version__ mismatch: "
            f"package={portable_ai_context.__version__!r} expected={expected_version!r}"
        )

    if importlib.util.find_spec("tiktoken") is not None:
        raise SystemExit("base wheel unexpectedly installed the optional tiktoken dependency")
    if importlib.util.find_spec("mcp") is not None:
        raise SystemExit("base wheel unexpectedly installed the optional MCP dependency")

    package_path = Path(portable_ai_context.__file__).resolve()
    if "site-packages" not in package_path.parts:
        raise SystemExit(f"package smoke is not using an installed wheel: {package_path}")

    script_name = "paic.exe" if sys.platform == "win32" else "paic"
    paic = Path(sys.executable).with_name(script_name)
    if not paic.is_file():
        raise SystemExit(f"installed wheel did not provide the paic console script at {paic}")

    version_run = subprocess.run(
        [str(paic), "--version"],
        check=True,
        capture_output=True,
        text=True,
    )
    expected_cli_version = f"paic {expected_version}"
    if version_run.stdout.strip() != expected_cli_version:
        raise SystemExit(
            f"paic --version mismatch: got={version_run.stdout.strip()!r} expected={expected_cli_version!r}"
        )

    help_run = subprocess.run(
        [str(paic), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    for command in ("conform", "checkpoint", "redact", "mcp"):
        if command not in help_run.stdout:
            raise SystemExit(f"paic --help did not expose the {command} command")
    if "Portable AI Context" not in help_run.stdout:
        raise SystemExit("paic --help did not expose the expected CLI")

    mcp_help_run = subprocess.run(
        [str(paic), "mcp", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    if "--root" not in mcp_help_run.stdout:
        raise SystemExit("installed-wheel MCP help did not expose the explicit --root boundary")

    compile_help_run = subprocess.run(
        [str(paic), "compile", "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    required_compile_help = (
        "--backend",
        "openai-compatible",
        "anthropic",
        "--anthropic-max-tokens",
        "gemini",
        "--gemini-max-output-tokens",
        "ollama",
        "--ollama-num-predict",
        "--ollama-api-key-env",
        "--token-counter",
        "tiktoken",
        "--tokenizer-model",
        "--tiktoken-encoding",
    )
    for marker in required_compile_help:
        if marker not in compile_help_run.stdout:
            raise SystemExit(
                f"installed-wheel compile help did not expose expected surface: {marker}"
            )

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fixture = root / "package-smoke.jsonl"
        fixture.write_text(
            "\n".join(
                [
                    json.dumps({"role": "user", "text": "package smoke question"}),
                    json.dumps({"role": "assistant", "text": "package smoke answer"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        _, inspect_report = _run_json([str(paic), "inspect", str(fixture)])
        conform_run, conform_report = _run_json(
            [str(paic), "conform", str(fixture)], check=False
        )
        if conform_run.returncode != 0:
            raise SystemExit("installed-wheel conform smoke returned nonzero")

        bundle = root / "package-smoke.aicb"
        subprocess.run(
            [str(paic), "bundle", str(fixture), "-o", str(bundle)],
            check=True,
            capture_output=True,
            text=True,
        )
        if not bundle.is_file():
            raise SystemExit("installed-wheel bundle smoke did not create an .aicb file")

        _, bundle_inspect_report = _run_json([str(paic), "inspect", str(bundle)])
        _, bundle_verify_report = _run_json([str(paic), "verify", str(bundle)])
        bundle_conform_run, bundle_conform_report = _run_json(
            [str(paic), "conform", str(bundle)], check=False
        )
        if bundle_conform_run.returncode != 0:
            raise SystemExit("installed-wheel bundle conform smoke returned nonzero")

        checkpoint_dir = root / "checkpoint-output"
        checkpoint_run = subprocess.run(
            [str(paic), "checkpoint", str(bundle), "-o", str(checkpoint_dir)],
            check=False,
            capture_output=True,
            text=True,
        )
        if checkpoint_run.returncode != 0:
            raise SystemExit("installed-wheel bundle checkpoint smoke returned nonzero")
        checkpoint_report_path = checkpoint_dir / "checkpoint-report.json"
        checkpoint_path = checkpoint_dir / "CHECKPOINT.md"
        if not checkpoint_report_path.is_file() or not checkpoint_path.is_file():
            raise SystemExit("installed-wheel checkpoint smoke did not create expected files")
        checkpoint_report = json.loads(checkpoint_report_path.read_text(encoding="utf-8"))

        fake_secret = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
        redaction_fixture = root / "redaction-smoke.jsonl"
        redaction_fixture.write_text(
            "\n".join(
                [
                    json.dumps({"role": "user", "text": f"synthetic secret {fake_secret}"}),
                    json.dumps({"role": "assistant", "text": "ordinary answer"}),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        redaction_dir = root / "redaction-review"
        redact_run, redact_payload = _run_json(
            [str(paic), "redact", str(redaction_fixture), "-o", str(redaction_dir)]
        )
        if redact_run.returncode != 0:
            raise SystemExit("installed-wheel redaction smoke returned nonzero")
        redaction_report_path = redaction_dir / "redaction-report.json"
        redacted_jsonl_path = redaction_dir / "conversation.redacted.jsonl"
        for expected in (
            redaction_dir / "conversation.redacted.clean.html",
            redaction_dir / "conversation.redacted.compact.txt",
            redacted_jsonl_path,
            redaction_report_path,
        ):
            if not expected.is_file():
                raise SystemExit(f"installed-wheel redaction smoke missed artifact: {expected.name}")
        redaction_report_text = redaction_report_path.read_text(encoding="utf-8")
        if fake_secret in redact_run.stdout or fake_secret in redaction_report_text:
            raise SystemExit("installed-wheel redaction smoke leaked the synthetic secret in report/stdout")
        redaction_report = json.loads(redaction_report_text)
        if redaction_report.get("affected_message_count") != 1:
            raise SystemExit("installed-wheel redaction smoke returned wrong affected message count")
        if redaction_report.get("supported_patterns_remaining") != 0:
            raise SystemExit("installed-wheel redaction smoke left a supported pattern")
        if redaction_report.get("manual_review_required") is not True:
            raise SystemExit("installed-wheel redaction smoke did not require manual review")
        if redaction_report.get("patterns_are_exhaustive") is not False:
            raise SystemExit("installed-wheel redaction smoke overstated pattern coverage")
        _, redacted_inspect_report = _run_json([str(paic), "inspect", str(redacted_jsonl_path)])
        if any(redacted_inspect_report["privacy"]["body_secret_counts"].values()):
            raise SystemExit("installed-wheel redaction smoke still detected a supported body pattern")
        if redact_payload.get("summary", {}).get("redacted_conversation_digest") != redaction_report.get(
            "redacted_conversation_digest"
        ):
            raise SystemExit("installed-wheel redaction stdout/report digest mismatch")

    if inspect_report.get("source") != "jsonl" or inspect_report.get("message_count") != 2:
        raise SystemExit(f"installed-wheel inspect smoke failed: {inspect_report!r}")
    if not conform_report.get("ok") or conform_report.get("source_kind") != "jsonl":
        raise SystemExit(f"installed-wheel conform smoke failed: {conform_report!r}")
    if conform_report.get("message_count") != 2:
        raise SystemExit("installed-wheel conform smoke returned wrong message count")

    if bundle_inspect_report.get("source") != "aicb" or bundle_inspect_report.get("message_count") != 2:
        raise SystemExit(f"installed-wheel AICB inspect smoke failed: {bundle_inspect_report!r}")
    if bundle_verify_report.get("message_count") != 2:
        raise SystemExit("installed-wheel AICB verify smoke returned wrong message count")
    if not bundle_conform_report.get("ok") or bundle_conform_report.get("source_kind") != "aicb":
        raise SystemExit(f"installed-wheel AICB conform smoke failed: {bundle_conform_report!r}")
    if bundle_conform_report.get("message_count") != 2:
        raise SystemExit("installed-wheel AICB conform smoke returned wrong message count")

    if checkpoint_report.get("policy") != "deterministic-extractive-v1":
        raise SystemExit("installed-wheel checkpoint smoke returned wrong policy")
    if checkpoint_report.get("profile") != "standard" or checkpoint_report.get("budget_tokens") != 16000:
        raise SystemExit("installed-wheel checkpoint smoke returned wrong default budget profile")
    if checkpoint_report.get("source_kind") != "aicb" or not checkpoint_report.get("budget_met"):
        raise SystemExit("installed-wheel AICB checkpoint smoke failed report validation")

    if redacted_inspect_report.get("source") != "jsonl" or redacted_inspect_report.get("message_count") != 2:
        raise SystemExit("installed-wheel redacted JSONL inspect smoke failed")

    print(
        json.dumps(
            {
                "ok": True,
                "distribution_version": installed_version,
                "package_version": portable_ai_context.__version__,
                "cli_version": version_run.stdout.strip(),
                "base_wheel_tiktoken_installed": False,
                "base_wheel_mcp_installed": False,
                "mcp_cli_surface": True,
                "compiler_backend_selector": True,
                "anthropic_backend_surface": True,
                "gemini_backend_surface": True,
                "ollama_backend_surface": True,
                "token_counter_selector": True,
                "redaction_review_surface": True,
                "redaction_manual_review_required": redaction_report["manual_review_required"],
                "source": inspect_report["source"],
                "message_count": inspect_report["message_count"],
                "conformance_ok": conform_report["ok"],
                "aicb_source": bundle_inspect_report["source"],
                "aicb_conformance_ok": bundle_conform_report["ok"],
                "checkpoint_policy": checkpoint_report["policy"],
                "checkpoint_budget_met": checkpoint_report["budget_met"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
