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

    with tempfile.TemporaryDirectory() as td:
        fixture = Path(td) / "package-smoke.jsonl"
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
        report = json.loads(inspect_run.stdout)

    if report.get("source") != "jsonl" or report.get("message_count") != 2:
        raise SystemExit(f"installed-wheel inspect smoke failed: {report!r}")

    print(
        json.dumps(
            {
                "ok": True,
                "distribution_version": installed_version,
                "package_version": portable_ai_context.__version__,
                "cli_version": version_run.stdout.strip(),
                "source": report["source"],
                "message_count": report["message_count"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
