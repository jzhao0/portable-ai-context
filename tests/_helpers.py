from __future__ import annotations

import json
from pathlib import Path

from portable_ai_context.models import Conversation, Message, SourceInfo, SnapshotInfo


def sample_conversation() -> Conversation:
    return Conversation(
        title="Synthetic Project",
        messages=[
            Message(role="user", text="Build feature A.", index=0),
            Message(role="assistant", text="Feature A is implemented.", index=1),
            Message(role="user", text="Now verify test B.", index=2),
            Message(role="assistant", text="Test B passed: 3/3.", index=3),
        ],
        source=SourceInfo(kind="synthetic"),
        snapshot=SnapshotInfo(created_at=1.0, updated_at=2.0, raw_node_count=4),
    )


def synthetic_chatgpt_html() -> str:
    # Minimal synthetic React flat-table payload understood by the ChatGPT adapter.
    table = []
    def put(value):
        table.append(value)
        return len(table) - 1

    k_linear = put("linear_conversation")
    k_title = put("title")
    k_create = put("create_time")
    k_update = put("update_time")
    k_message = put("message")
    k_author = put("author")
    k_role = put("role")
    k_content = put("content")
    k_content_type = put("content_type")
    k_parts = put("parts")
    s_user = put("user")
    s_assistant = put("assistant")
    s_text = put("text")
    s_hello = put("Hello from user")
    s_hi = put("Hello from assistant")
    s_title = put("Synthetic Share")

    user_author = put({f"_{k_role}": s_user})
    user_parts = put([s_hello])
    user_content = put({f"_{k_content_type}": s_text, f"_{k_parts}": user_parts})
    user_msg = put({f"_{k_author}": user_author, f"_{k_content}": user_content})
    user_node = put({f"_{k_message}": user_msg})

    assistant_author = put({f"_{k_role}": s_assistant})
    assistant_parts = put([s_hi])
    assistant_content = put({f"_{k_content_type}": s_text, f"_{k_parts}": assistant_parts})
    assistant_msg = put({f"_{k_author}": assistant_author, f"_{k_content}": assistant_content})
    assistant_node = put({f"_{k_message}": assistant_msg})

    linear = put([user_node, assistant_node])
    create_v = put(100.0)
    update_v = put(200.0)
    put({
        f"_{k_linear}": linear,
        f"_{k_title}": s_title,
        f"_{k_create}": create_v,
        f"_{k_update}": update_v,
    })

    encoded = json.dumps(json.dumps(table))
    return f"<!doctype html><script>streamController.enqueue({encoded})</script>"
