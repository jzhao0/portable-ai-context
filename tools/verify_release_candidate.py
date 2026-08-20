from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


ALPHA_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+a[0-9]+$")
CHECKSUM_LINE_RE = re.compile(r"^(?P<digest>[0-9a-f]{64})  (?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)$")


class CandidateVerificationError(RuntimeError):
    pass


def _expected_names(version: str) -> tuple[str, str]:
    if not isinstance(version, str) or not ALPHA_VERSION_RE.fullmatch(version):
        raise CandidateVerificationError("release version must use alpha convention X.Y.ZaN")
    normalized = version.replace("-", "_")
    return (
        f"portable_ai_context-{normalized}-py3-none-any.whl",
        f"portable_ai_context-{normalized}.tar.gz",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise CandidateVerificationError("release candidate artifact could not be read") from exc
    return digest.hexdigest()


def _read_checksums(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        raise CandidateVerificationError("release candidate checksum file could not be read") from exc

    lines = text.splitlines()
    if len(lines) != 2 or any(not line for line in lines):
        raise CandidateVerificationError("SHA256SUMS must contain exactly two non-empty entries")

    result: dict[str, str] = {}
    for line in lines:
        match = CHECKSUM_LINE_RE.fullmatch(line)
        if match is None:
            raise CandidateVerificationError("SHA256SUMS contains a malformed entry")
        name = match.group("name")
        if name in result:
            raise CandidateVerificationError("SHA256SUMS contains a duplicate filename")
        result[name] = match.group("digest")
    return result


def verify_candidate(
    *,
    version: str,
    artifacts_dir: Path,
    checksums: Path,
) -> dict[str, object]:
    wheel, sdist = _expected_names(version)
    expected = {wheel, sdist}

    try:
        if not artifacts_dir.is_dir():
            raise CandidateVerificationError("release candidate artifact directory does not exist")
        files = [path for path in artifacts_dir.iterdir() if path.is_file()]
    except OSError as exc:
        raise CandidateVerificationError("release candidate artifact directory could not be read") from exc

    names = {path.name for path in files}
    if len(files) != 2 or names != expected:
        raise CandidateVerificationError("release candidate artifact set is not the exact expected wheel/sdist pair")

    recorded = _read_checksums(checksums)
    if set(recorded) != expected:
        raise CandidateVerificationError("SHA256SUMS filename set does not match the exact release candidate")

    actual: dict[str, str] = {}
    for name in sorted(expected):
        digest = _sha256(artifacts_dir / name)
        actual[name] = digest
        if recorded[name] != digest:
            raise CandidateVerificationError(f"SHA256 mismatch for expected release artifact {name}")

    return {
        "ok": True,
        "version": version,
        "wheel": wheel,
        "sdist": sdist,
        "artifact_sha256": actual,
        "read_only_verification": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify retained release-candidate wheel/sdist bytes against SHA256SUMS without modifying them."
    )
    parser.add_argument("--version", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    parser.add_argument("--checksums", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = verify_candidate(
            version=args.version,
            artifacts_dir=Path(args.artifacts_dir),
            checksums=Path(args.checksums),
        )
    except CandidateVerificationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
