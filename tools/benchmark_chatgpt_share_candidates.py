"""Offline synthetic ChatGPT flat-table candidate benchmark.

Run from checkout root:
    PYTHONPATH=src python tools/benchmark_chatgpt_share_candidates.py

Reports separate normal (one key) and repeated-key stress workloads.
No private transcripts or network calls are used.
"""
from __future__ import annotations

import statistics
import time

from portable_ai_context.adapters.chatgpt_html import (
    FlatTableResolver,
    _number,
    find_conversation,
)


def previous_lookup(tables):
    candidates = []
    for table_index, table in enumerate(tables):
        key_indices = [i for i, item in enumerate(table) if item == "linear_conversation"]
        if not key_indices:
            continue
        resolver = FlatTableResolver(table)
        for key_index in key_indices:
            encoded_key = f"_{key_index}"
            for item_index, item in enumerate(table):
                if not isinstance(item, dict) or encoded_key not in item:
                    continue
                linear = resolver.resolve(item[encoded_key])
                if not isinstance(linear, list) or not linear:
                    continue
                conv = {"linear_conversation": linear}
                for raw_key, raw_value in item.items():
                    if isinstance(raw_key, str) and raw_key.startswith("_") and raw_key[1:].isdigit():
                        key = resolver.resolve(int(raw_key[1:]))
                    else:
                        key = raw_key
                    if key in {"title", "create_time", "update_time", "default_model_slug"}:
                        conv[key] = resolver.resolve(raw_value) if isinstance(raw_value, int) else raw_value
                conv["_candidate_table"] = table_index
                conv["_candidate_item"] = item_index
                candidates.append(conv)
    if not candidates:
        raise RuntimeError("expected at least one synthetic candidate")
    return max(
        candidates,
        key=lambda c: (
            _number(c.get("update_time")),
            len(c.get("linear_conversation", [])),
            _number(c.get("create_time")),
        ),
    )


def fixture(size: int, markers: int):
    table = ["synthetic filler"] * size
    table[0] = "title"
    table[1] = [{"message": "synthetic-only"}]
    for index in range(2, markers + 2):
        table[index] = "linear_conversation"
    table[-3] = {"_2": 1, "title": "A", "update_time": 5.0}
    table[-2] = {"_3": 1, "title": "B", "update_time": 10.0}
    table[-1] = {"_4": 1, "title": "C", "update_time": 20.0}
    return [table]


def median_seconds(fn, data, runs: int = 5):
    samples = []
    for _ in range(runs):
        start = time.perf_counter()
        fn(data)
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def main():
    print("items,marker_positions,old_seconds,new_seconds,speedup,same_candidate")
    for rows, markers in ((1000, 1), (2000, 25), (8000, 100), (12000, 200)):
        inputs = fixture(rows, markers)
        before = previous_lookup(inputs)
        after = find_conversation(inputs)
        assert before == after, "candidate selection changed"
        old_t = median_seconds(previous_lookup, inputs)
        new_t = median_seconds(find_conversation, inputs)
        print(f"{rows},{markers},{old_t:.6f},{new_t:.6f},{old_t / new_t:.2f},true")


if __name__ == "__main__":
    main()
