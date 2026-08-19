from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+a[0-9]+$")
CHECKSUM_RE = re.compile(r"^([0-9a-f]{64})  ([^/\\]+)$")


class SubjectVerificationError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_subjects(*, version: str, artifacts_dir: Path) -> dict[str, object]:
    if not VERSION_RE.fullmatch(version):
        raise SubjectVerificationError("release version must use alpha convention X.Y.ZaN")
    if not artifacts_dir.is_dir():
        raise SubjectVerificationError("release artifact directory does not exist")

    wheel_name = f"portable_ai_context-{version}-py3-none-any.whl"
    sdist_name = f"portable_ai_context-{version}.tar.gz"
    wheel = artifacts_dir / "dist" / wheel_name
    sdist = artifacts_dir / "dist" / sdist_name
    checksums = artifacts_dir / "SHA256SUMS"

    files = sorted(path for path in artifacts_dir.rglob("*") if path.is_file())
    expected = {wheel.resolve(), sdist.resolve(), checksums.resolve()}
    actual = {path.resolve() for path in files}
    if actual != expected:
        raise SubjectVerificationError("release attestation subjects do not match the exact expected file set")

    lines = [line for line in checksums.read_text(encoding="utf-8").splitlines() if line]
    if len(lines) != 2:
        raise SubjectVerificationError("SHA256SUMS must contain exactly two entries")

    recorded: dict[str, str] = {}
    for line in lines:
        match = CHECKSUM_RE.fullmatch(line)
        if not match:
            raise SubjectVerificationError("SHA256SUMS contains an invalid entry")
        digest, name = match.groups()
        if name in recorded:
            raise SubjectVerificationError("SHA256SUMS contains a duplicate entry")
        recorded[name] = digest

    if set(recorded) != {wheel_name, sdist_name}:
        raise SubjectVerificationError("SHA256SUMS file set does not match expected wheel and sdist")

    wheel_sha = _sha256(wheel)
    sdist_sha = _sha256(sdist)
    if recorded[wheel_name] != wheel_sha:
        raise SubjectVerificationError("wheel SHA256 does not match SHA256SUMS")
    if recorded[sdist_name] != sdist_sha:
        raise SubjectVerificationError("sdist SHA256 does not match SHA256SUMS")

    return {
        "ok": True,
        "version": version,
        "subjects": [wheel_name, sdist_name, "SHA256SUMS"],
        "wheel_sha256": wheel_sha,
        "sdist_sha256": sdist_sha,
        "checksum_entries": 2,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify exact release attestation subject files and checksums.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--artifacts-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = verify_subjects(
            version=args.version,
            artifacts_dir=Path(args.artifacts_dir),
        )
    except (SubjectVerificationError, OSError, UnicodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
