from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parents[1]


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
    if "Portable AI Context" not in help_run.stdout:
        raise SystemExit("paic --help did not expose the expected CLI")
    if "conform" not in help_run.stdout:
        raise SystemExit("paic --help did not expose the conform command")
    if "checkpoint" not in help_run.stdout:
        raise SystemExit("paic --help did not expose the checkpoint command")

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
        inspect_run = subprocess.run(
            [str(paic), "inspect", str(fixture)],
            check=True,
            capture_output=True,
            text=True,
        )
        inspect_report = json.loads(inspect_run.stdout)

        conform_run = subprocess.run(
            [str(paic), "conform", str(fixture)],
            check=False,
            capture_output=True,
            text=True,
        )
        if conform_run.returncode != 0:
            raise SystemExit("installed-wheel conform smoke returned nonzero")
        conform_report = json.loads(conform_run.stdout)

        checkpoint_dir = root / "checkpoint-output"
        checkpoint_run = subprocess.run(
            [str(paic), "checkpoint", str(fixture), "-o", str(checkpoint_dir)],
            check=False,
            capture_output=True,
            text=True,
        )
        if checkpoint_run.returncode != 0:
            raise SystemExit("installed-wheel checkpoint smoke returned nonzero")
        checkpoint_report_path = checkpoint_dir / "checkpoint-report.json"
        checkpoint_path = checkpoint_dir / "CHECKPOINT.md"
        if not checkpoint_report_path.is_file() or not checkpoint_path.is_file():
            raise SystemExit("installed-wheel checkpoint smoke did not create expected files")
        checkpoint_report = json.loads(checkpoint_report_path.read_text(encoding="utf-8"))

    if inspect_report.get("source") != "jsonl" or inspect_report.get("message_count") != 2:
        raise SystemExit(f"installed-wheel inspect smoke failed: {inspect_report!r}")
    if not conform_report.get("ok") or conform_report.get("source_kind") != "jsonl":
        raise SystemExit(f"installed-wheel conform smoke failed: {conform_report!r}")
    if conform_report.get("message_count") != 2:
        raise SystemExit("installed-wheel conform smoke returned wrong message count")
    if checkpoint_report.get("policy") != "deterministic-extractive-v1":
        raise SystemExit("installed-wheel checkpoint smoke returned wrong policy")
    if checkpoint_report.get("profile") != "standard" or checkpoint_report.get("budget_tokens") != 16000:
        raise SystemExit("installed-wheel checkpoint smoke returned wrong default budget profile")
    if checkpoint_report.get("source_kind") != "jsonl" or not checkpoint_report.get("budget_met"):
        raise SystemExit("installed-wheel checkpoint smoke failed report validation")

    print(
        json.dumps(
            {
                "ok": True,
                "distribution_version": installed_version,
                "package_version": portable_ai_context.__version__,
                "cli_version": version_run.stdout.strip(),
                "source": inspect_report["source"],
                "message_count": inspect_report["message_count"],
                "conformance_ok": conform_report["ok"],
                "checkpoint_policy": checkpoint_report["policy"],
                "checkpoint_budget_met": checkpoint_report["budget_met"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
