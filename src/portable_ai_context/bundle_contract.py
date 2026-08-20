from __future__ import annotations


AICB_SCHEMA_VERSION = "0.1-alpha"

# Stable ordering is used by the writer/manifest for reproducible contract shape;
# the reader validates the member set independently of ZIP member order.
AICB_MEMBER_ORDER = (
    "manifest.json",
    "conversation.jsonl",
    "integrity.json",
    "privacy.json",
)
AICB_REQUIRED_MEMBERS = frozenset(AICB_MEMBER_ORDER)
