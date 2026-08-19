from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
TAG_RE = re.compile(r"^v(?P<version>[0-9]+\.[0-9]+\.[0-9]+a[0-9]+)$")
PROJECT_SECTION_RE = re.compile(r"(?ms)^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)")
PROJECT_VERSION_RE = re.compile(r'(?m)^version\s*=\s*["\'](?P<version>[^"\']+)["\']\s*$')


class ReleaseGuardError(RuntimeError):
    pass


def _project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    section = PROJECT_SECTION_RE.search(text)
    if not section:
        raise ReleaseGuardError("[project] section is missing from pyproject.toml")
    match = PROJECT_VERSION_RE.search(section.group("body"))
    if not match:
        raise ReleaseGuardError("project version is missing")
    return match.group("version")


def _package_version() -> str:
    init_path = ROOT / "src" / "portable_ai_context" / "__init__.py"
    text = init_path.read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$', text, re.MULTILINE)
    if not match:
        raise ReleaseGuardError("package __version__ is missing")
    return match.group(1)


def _git(*args: str) -> str:
    run = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        raise ReleaseGuardError(f"git command failed: {' '.join(args)}")
    return run.stdout.strip()


def _validate_tag(tag: str, expected_version: str) -> str:
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise ReleaseGuardError("release tag must use alpha convention vX.Y.ZaN")
    tag_version = match.group("version")
    if tag_version != expected_version:
        raise ReleaseGuardError(
            f"tag/project version mismatch: tag={tag_version!r} project={expected_version!r}"
        )

    head = _git("rev-parse", "HEAD")
    tagged = _git("rev-parse", f"refs/tags/{tag}^{{commit}}")
    if head != tagged:
        raise ReleaseGuardError("checked-out HEAD does not match the requested release tag")
    return head


def _validate_changelog(version: str, mode: str) -> None:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = [line.strip() for line in text.splitlines() if line.startswith("## ")]
    matching = [line for line in headings if line.startswith(f"## {version}")]
    if len(matching) != 1:
        raise ReleaseGuardError(f"CHANGELOG must contain exactly one heading for {version}")
    if mode == "publish" and "unreleased" in matching[0].casefold():
        raise ReleaseGuardError("publish mode refuses a CHANGELOG entry still marked Unreleased")


def _expected_artifact_names(version: str) -> set[str]:
    normalized = version.replace("-", "_")
    return {
        f"portable_ai_context-{normalized}-py3-none-any.whl",
        f"portable_ai_context-{normalized}.tar.gz",
    }


def _write_checksums(artifacts_dir: Path, output: Path, version: str) -> dict[str, str]:
    if not artifacts_dir.is_dir():
        raise ReleaseGuardError("artifact directory does not exist")

    files = sorted(
        [path for path in artifacts_dir.iterdir() if path.is_file() and path.suffix == ".whl"]
        + [path for path in artifacts_dir.iterdir() if path.is_file() and path.name.endswith(".tar.gz")],
        key=lambda path: path.name,
    )
    names = {path.name for path in files}
    expected = _expected_artifact_names(version)
    if names != expected:
        raise ReleaseGuardError(
            f"release artifacts do not match expected wheel/sdist set: got={sorted(names)!r} expected={sorted(expected)!r}"
        )

    digests: dict[str, str] = {}
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        digests[path.name] = digest

    output.write_text(
        "".join(f"{digest}  {name}\n" for name, digest in sorted(digests.items())),
        encoding="utf-8",
    )
    return digests


def validate_release(
    *,
    tag: str,
    mode: str,
    artifacts_dir: Path | None = None,
    checksums: Path | None = None,
) -> dict[str, object]:
    if mode not in {"dry-run", "publish"}:
        raise ReleaseGuardError("mode must be dry-run or publish")

    project_version = _project_version()
    package_version = _package_version()
    if package_version != project_version:
        raise ReleaseGuardError(
            f"project/package version mismatch: project={project_version!r} package={package_version!r}"
        )

    commit = _validate_tag(tag, project_version)
    _validate_changelog(project_version, mode)

    artifact_digests: dict[str, str] | None = None
    if artifacts_dir is not None:
        if checksums is None:
            raise ReleaseGuardError("--checksums is required with --artifacts-dir")
        artifact_digests = _write_checksums(artifacts_dir, checksums, project_version)

    return {
        "ok": True,
        "mode": mode,
        "tag": tag,
        "version": project_version,
        "commit": commit,
        "artifact_sha256": artifact_digests,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed release tag/version/artifact validation.")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--mode", choices=["dry-run", "publish"], default="dry-run")
    parser.add_argument("--artifacts-dir")
    parser.add_argument("--checksums")
    parser.add_argument("--github-output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = validate_release(
            tag=args.tag,
            mode=args.mode,
            artifacts_dir=Path(args.artifacts_dir) if args.artifacts_dir else None,
            checksums=Path(args.checksums) if args.checksums else None,
        )
    except (ReleaseGuardError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.github_output:
        output = Path(args.github_output)
        with output.open("a", encoding="utf-8") as handle:
            handle.write(f"version={report['version']}\n")
            handle.write(f"commit={report['commit']}\n")

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
