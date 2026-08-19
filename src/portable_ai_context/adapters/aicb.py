from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any
import zipfile

from portable_ai_context.conformance import SOURCE_KIND_RE
from portable_ai_context.errors import ParseError
from portable_ai_context.integrity import inspect as inspect_integrity
from portable_ai_context.models import Conversation, SourceInfo
from portable_ai_context.privacy import BODY_PATTERNS, inspect_conversation
from . import jsonl


SCHEMA_VERSION = "0.1-alpha"
SOURCE_KIND = "aicb"
REQUIRED_MEMBERS = frozenset(
    {"manifest.json", "conversation.jsonl", "integrity.json", "privacy.json"}
)
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_MEMBER_BYTES = 96 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_MEMBER_COUNT = 8
_SUPPORTED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_METADATA_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")

_CANONICAL_INTEGRITY_FIELDS = (
    "message_count",
    "user_count",
    "assistant_count",
    "conversation_digest",
    "first_message_hash",
    "last_message_hash",
    "last_user_hash",
    "last_assistant_hash",
)


def can_load(source: str) -> bool:
    return Path(source).suffix.lower() == ".aicb"


def _fail(message: str) -> ParseError:
    return ParseError(f"AICB bundle contract violation: {message}")


def _is_nonnegative_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _validate_member_name(name: str) -> None:
    if not isinstance(name, str) or not name:
        raise _fail("archive contains an invalid member name")
    if "\\" in name:
        raise _fail("archive member uses backslash path syntax")
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name):
        raise _fail("archive contains an absolute-path member")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"..", "."} for part in path.parts):
        raise _fail("archive contains a traversal-style member path")
    if len(path.parts) != 1:
        raise _fail("alpha bundles may contain root-level members only")


def _validate_zip_metadata(infos: list[zipfile.ZipInfo]) -> dict[str, zipfile.ZipInfo]:
    if len(infos) > MAX_MEMBER_COUNT:
        raise _fail("archive contains too many members")

    by_name: dict[str, zipfile.ZipInfo] = {}
    total_uncompressed = 0
    for info in infos:
        _validate_member_name(info.filename)
        if info.filename in by_name:
            raise _fail("archive contains a duplicate member name")
        if info.is_dir():
            raise _fail("archive contains an unexpected directory entry")
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if unix_mode and stat.S_ISLNK(unix_mode):
            raise _fail("archive contains a symlink-like member")
        if info.flag_bits & 0x1:
            raise _fail("encrypted archive members are unsupported")
        if info.compress_type not in _SUPPORTED_COMPRESSION:
            raise _fail("archive uses an unsupported compression method")
        if info.file_size < 0 or info.file_size > MAX_MEMBER_BYTES:
            raise _fail("archive member exceeds the alpha size limit")
        total_uncompressed += info.file_size
        if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise _fail("archive exceeds the alpha uncompressed-size limit")
        by_name[info.filename] = info

    names = frozenset(by_name)
    if names != REQUIRED_MEMBERS:
        missing = REQUIRED_MEMBERS - names
        extra = names - REQUIRED_MEMBERS
        if missing:
            raise _fail("archive is missing a required member")
        if extra:
            raise _fail("archive contains an unexpected member")
        raise _fail("archive member set is invalid")
    return by_name


def _read_member(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    try:
        with zf.open(info, "r") as handle:
            data = handle.read(MAX_MEMBER_BYTES + 1)
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        raise _fail("archive member could not be read safely") from exc
    if len(data) > MAX_MEMBER_BYTES:
        raise _fail("archive member exceeds the alpha read limit")
    if len(data) != info.file_size:
        raise _fail("archive member size metadata is inconsistent")
    return data


def _decode_utf8(name: str, data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _fail(f"{name} is not valid UTF-8") from exc


def _load_json_object(name: str, text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _fail(f"{name} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise _fail(f"{name} must contain a JSON object")
    return value


def _validate_manifest(manifest: dict[str, Any]) -> tuple[str, int, str, str]:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise _fail("manifest declares an unsupported schema version")
    if not isinstance(manifest.get("created_at"), str) or not manifest["created_at"].strip():
        raise _fail("manifest created_at is invalid")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or any(not isinstance(item, str) for item in artifacts):
        raise _fail("manifest artifact list is invalid")
    if len(artifacts) != len(REQUIRED_MEMBERS) or len(set(artifacts)) != len(artifacts):
        raise _fail("manifest artifact list is inconsistent")
    if frozenset(artifacts) != REQUIRED_MEMBERS:
        raise _fail("manifest artifact list does not match the alpha bundle contract")

    conversation = manifest.get("conversation")
    if not isinstance(conversation, dict):
        raise _fail("manifest conversation metadata is invalid")
    title = conversation.get("title")
    message_count = conversation.get("message_count")
    digest = conversation.get("digest")
    original_source_kind = conversation.get("source_kind")
    if not isinstance(title, str):
        raise _fail("manifest conversation title is invalid")
    if not _is_nonnegative_int(message_count):
        raise _fail("manifest message count is invalid")
    if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
        raise _fail("manifest conversation digest is invalid")
    if not isinstance(original_source_kind, str) or not SOURCE_KIND_RE.fullmatch(original_source_kind):
        raise _fail("manifest original source kind is not a safe identifier")
    return title, message_count, digest, original_source_kind


def _validate_bundle_jsonl_shape(text: str) -> None:
    seen = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        seen += 1
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise _fail(f"conversation.jsonl line {lineno} is invalid JSON") from exc
        if not isinstance(value, dict) or set(value) != {"role", "text"}:
            raise _fail(f"conversation.jsonl line {lineno} is not a canonical bundle record")
        if value.get("role") not in {"user", "assistant"}:
            raise _fail(f"conversation.jsonl line {lineno} has a noncanonical role")
        body = value.get("text")
        if not isinstance(body, str) or not body.strip():
            raise _fail(f"conversation.jsonl line {lineno} has invalid text")
    if not seen:
        raise _fail("conversation.jsonl contains no records")


def _validate_hash_or_none(value: Any) -> bool:
    return value is None or (isinstance(value, str) and bool(_HEX64_RE.fullmatch(value)))


def _validate_integrity_record(recorded: dict[str, Any], actual: dict[str, Any]) -> None:
    for key in ("message_count", "user_count", "assistant_count"):
        if not _is_nonnegative_int(recorded.get(key)):
            raise _fail(f"integrity.json field {key} is invalid")
    if not isinstance(recorded.get("conversation_digest"), str) or not _HEX64_RE.fullmatch(
        recorded["conversation_digest"]
    ):
        raise _fail("integrity.json conversation digest is invalid")
    for key in ("first_message_hash", "last_message_hash", "last_user_hash", "last_assistant_hash"):
        if not _validate_hash_or_none(recorded.get(key)):
            raise _fail(f"integrity.json field {key} is invalid")

    for key in _CANONICAL_INTEGRITY_FIELDS:
        if recorded.get(key) != actual.get(key):
            raise _fail(f"integrity.json canonical field mismatch: {key}")


def _validate_count_mapping(value: Any, *, name: str, allowed_keys: set[str] | None = None) -> dict[str, int]:
    if not isinstance(value, dict):
        raise _fail(f"privacy.json {name} is invalid")
    result: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not _SAFE_METADATA_KEY_RE.fullmatch(key):
            raise _fail(f"privacy.json {name} contains an invalid key")
        if allowed_keys is not None and key not in allowed_keys:
            raise _fail(f"privacy.json {name} contains an unexpected key")
        if not _is_nonnegative_int(count):
            raise _fail(f"privacy.json {name} contains an invalid count")
        result[key] = count
    return result


def _validate_privacy_record(recorded: dict[str, Any], conversation: Conversation) -> dict[str, int]:
    runtime_counts = _validate_count_mapping(
        recorded.get("runtime_marker_counts"), name="runtime_marker_counts"
    )
    body_counts = _validate_count_mapping(
        recorded.get("body_secret_counts"),
        name="body_secret_counts",
        allowed_keys=set(BODY_PATTERNS),
    )
    if set(body_counts) != set(BODY_PATTERNS):
        raise _fail("privacy.json body_secret_counts is incomplete")
    safe_flag = recorded.get("safe_to_share_automatically")
    if not isinstance(safe_flag, bool):
        raise _fail("privacy.json safe_to_share_automatically is invalid")

    recomputed = inspect_conversation(conversation)
    if body_counts != recomputed.body_secret_counts:
        raise _fail("privacy.json body-secret counts do not match canonical content")
    if safe_flag != recomputed.safe_to_share_automatically:
        raise _fail("privacy.json share-safety flag does not match canonical content")
    return runtime_counts


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def load(source: str) -> Conversation:
    path = Path(source).expanduser().resolve()
    try:
        archive_size = path.stat().st_size
    except OSError as exc:
        raise _fail("archive metadata could not be read") from exc
    if archive_size > MAX_ARCHIVE_BYTES:
        raise _fail("archive exceeds the alpha compressed-size limit")

    try:
        with zipfile.ZipFile(path, "r") as zf:
            by_name = _validate_zip_metadata(zf.infolist())
            payloads = {
                name: _decode_utf8(name, _read_member(zf, by_name[name]))
                for name in REQUIRED_MEMBERS
            }
    except ParseError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise _fail("input is not a valid readable ZIP bundle") from exc

    manifest = _load_json_object("manifest.json", payloads["manifest.json"])
    title, expected_count, expected_digest, original_source_kind = _validate_manifest(manifest)

    conversation_text = payloads["conversation.jsonl"]
    _validate_bundle_jsonl_shape(conversation_text)
    try:
        conversation = jsonl.load("conversation.jsonl", conversation_text)
    except ParseError as exc:
        raise _fail("conversation.jsonl failed canonical parsing") from exc
    conversation.title = title

    actual_integrity = inspect_integrity(conversation).to_dict()
    if actual_integrity["message_count"] != expected_count:
        raise _fail("manifest message count does not match canonical conversation")
    if actual_integrity["conversation_digest"] != expected_digest:
        raise _fail("manifest digest does not match canonical conversation")

    recorded_integrity = _load_json_object("integrity.json", payloads["integrity.json"])
    _validate_integrity_record(recorded_integrity, actual_integrity)

    recorded_privacy = _load_json_object("privacy.json", payloads["privacy.json"])
    runtime_counts = _validate_privacy_record(recorded_privacy, conversation)

    conversation.source = SourceInfo(
        kind=SOURCE_KIND,
        locator=str(path),
        fingerprint=_file_sha256(path),
        metadata={
            "bundle_schema_version": SCHEMA_VERSION,
            "bundle_original_source_kind": original_source_kind,
            "bundle_integrity_verified": True,
            "bundle_recorded_runtime_marker_counts": runtime_counts,
        },
    )
    return conversation
