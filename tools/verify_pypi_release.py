from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request


class VerificationError(RuntimeError):
    pass


def load_checksums(path: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2:
            raise VerificationError("invalid SHA256SUMS line")
        digest, filename = parts
        if len(digest) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in digest):
            raise VerificationError("invalid SHA256 digest in SHA256SUMS")
        if filename in expected:
            raise VerificationError("duplicate filename in SHA256SUMS")
        expected[filename] = digest.lower()
    if not expected:
        raise VerificationError("SHA256SUMS is empty")
    return expected


def fetch_release(project: str, version: str, *, timeout: int = 30) -> dict:
    url = f"https://pypi.org/pypi/{project}/{version}/json"
    request = urllib.request.Request(url, headers={"User-Agent": "portable-ai-context-release-verifier"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def verify_payload(payload: dict, expected: dict[str, str], version: str) -> dict[str, str]:
    info = payload.get("info")
    if not isinstance(info, dict) or info.get("version") != version:
        raise VerificationError("PyPI release metadata version does not match expected version")

    urls = payload.get("urls")
    if not isinstance(urls, list):
        raise VerificationError("PyPI release response contains no file list")

    actual: dict[str, str] = {}
    for item in urls:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename")
        digests = item.get("digests")
        sha256 = digests.get("sha256") if isinstance(digests, dict) else None
        if isinstance(filename, str) and isinstance(sha256, str):
            actual[filename] = sha256.lower()

    if actual != expected:
        raise VerificationError(
            f"PyPI artifact hash set mismatch: published={sorted(actual)!r} expected={sorted(expected)!r}"
        )
    return actual


def verify_with_retry(
    *,
    project: str,
    version: str,
    checksums: Path,
    attempts: int,
    delay_seconds: float,
) -> dict[str, object]:
    if attempts <= 0:
        raise VerificationError("attempts must be positive")
    if delay_seconds < 0:
        raise VerificationError("delay must not be negative")

    expected = load_checksums(checksums)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            payload = fetch_release(project, version)
            actual = verify_payload(payload, expected, version)
            return {
                "ok": True,
                "project": project,
                "version": version,
                "files": actual,
                "attempt": attempt,
            }
        except (VerificationError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(delay_seconds)

    if isinstance(last_error, VerificationError):
        raise last_error
    raise VerificationError(
        f"PyPI release metadata was not available after {attempts} attempts ({type(last_error).__name__})"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify published PyPI file hashes against SHA256SUMS.")
    parser.add_argument("--project", default="portable-ai-context")
    parser.add_argument("--version", required=True)
    parser.add_argument("--checksums", required=True)
    parser.add_argument("--attempts", type=int, default=12)
    parser.add_argument("--delay-seconds", type=float, default=10.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = verify_with_retry(
            project=args.project,
            version=args.version,
            checksums=Path(args.checksums),
            attempts=args.attempts,
            delay_seconds=args.delay_seconds,
        )
    except (VerificationError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
