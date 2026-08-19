from __future__ import annotations

import json
from pathlib import Path
import sys
from zipfile import BadZipFile, ZipFile


EXPECTED_PERMISSIONS = {"activeTab", "scripting"}
EXPECTED_GECKO_ID = "portable-ai-context-capture@jzhao0.github.io"
REQUIRED_FILES = {
    "manifest.json",
    "popup.html",
    "popup.css",
    "popup.js",
}
FORBIDDEN_MANIFEST_KEYS = {
    "host_permissions",
    "optional_host_permissions",
}
FORBIDDEN_PERMISSIONS = {
    "cookies",
    "webRequest",
    "webRequestBlocking",
    "tabs",
    "storage",
    "downloads",
    "debugger",
    "history",
    "clipboardRead",
    "clipboardWrite",
    "nativeMessaging",
}


def fail(message: str) -> None:
    raise SystemExit(message)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    artifact_dir = Path(args[0]) if args else Path("firefox-extension-dist")

    archives = sorted(artifact_dir.glob("*.zip"))
    if len(archives) != 1:
        fail(f"expected exactly one Firefox extension ZIP, found {len(archives)}")

    archive = archives[0]
    try:
        with ZipFile(archive) as package:
            names = set(package.namelist())
            missing = sorted(REQUIRED_FILES - names)
            if missing:
                fail("Firefox package is missing required top-level files: " + ", ".join(missing))
            if any(name.startswith("/") or ".." in Path(name).parts for name in names):
                fail("Firefox package contains unsafe member paths")

            manifest_raw = package.read("manifest.json")
    except (BadZipFile, KeyError) as exc:
        fail(f"invalid Firefox extension package: {type(exc).__name__}")

    try:
        manifest = json.loads(manifest_raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail(f"packaged Firefox manifest is invalid JSON: {type(exc).__name__}")

    if not isinstance(manifest, dict):
        fail("packaged Firefox manifest must be a JSON object")
    if manifest.get("manifest_version") != 3:
        fail("packaged Firefox manifest is not Manifest V3")

    permissions = manifest.get("permissions")
    if not isinstance(permissions, list) or set(permissions) != EXPECTED_PERMISSIONS:
        fail("packaged Firefox permissions differ from activeTab+scripting")
    if FORBIDDEN_PERMISSIONS.intersection(permissions):
        fail("packaged Firefox manifest contains a forbidden permission")
    for key in FORBIDDEN_MANIFEST_KEYS:
        if key in manifest:
            fail(f"packaged Firefox manifest unexpectedly contains {key}")

    settings = manifest.get("browser_specific_settings")
    if not isinstance(settings, dict):
        fail("packaged Firefox manifest is missing browser_specific_settings")
    gecko = settings.get("gecko")
    if not isinstance(gecko, dict):
        fail("packaged Firefox manifest is missing gecko settings")
    if gecko.get("id") != EXPECTED_GECKO_ID:
        fail("packaged Firefox manifest has an unexpected Gecko extension ID")
    if "strict_min_version" in gecko:
        fail("Firefox runtime baseline must not be claimed before the live smoke")

    collection = gecko.get("data_collection_permissions")
    if collection != {"required": ["none"]}:
        fail("packaged Firefox data collection declaration must be required=[none]")

    print(
        json.dumps(
            {
                "ok": True,
                "package": archive.name,
                "manifest_version": 3,
                "permissions": sorted(EXPECTED_PERMISSIONS),
                "host_permissions": False,
                "gecko_id": EXPECTED_GECKO_ID,
                "data_collection_required": ["none"],
                "strict_min_version_claimed": False,
                "required_files_present": True,
                "evidence_scope": "package_only_not_live_runtime",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
