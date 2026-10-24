"""Synthetic differential tests for ChatGPT share flat-table candidate lookup."""
from __future__ import annotations

import unittest

from portable_ai_context.adapters.chatgpt_html import (
    FlatTableResolver,
    ParseError,
    _number,
    find_conversation,
)


def reference_find_conversation(tables):
    """Unmodified prior nested-scan candidate order and tie policy."""
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
        raise ParseError("linear_conversation not found")
    return max(
        candidates,
        key=lambda c: (
            _number(c.get("update_time")),
            len(c.get("linear_conversation", [])),
            _number(c.get("create_time")),
        ),
    )


def sample_table(size: int, marker_count: int):
    table = ["noise"] * size
    table[0] = "title"
    table[1] = [{"message": "synthetic"}]
    for index in range(2, marker_count + 2):
        table[index] = "linear_conversation"
    table[-3] = {"_2": 1, "title": "first", "update_time": 10.5}
    table[-2] = {"_3": 1, "title": "second", "update_time": 10.5}
    table[-1] = {"_4": 1, "title": "third", "update_time": 99.0}
    return table


class SharedFlatTableLookupTests(unittest.TestCase):
    def test_tie_prefers_earlier_key_even_if_item_is_later(self):
        table = [
            "title", "linear_conversation", "linear_conversation",
            [{"synthetic": "one"}], [{"synthetic": "two"}],
            {"_2": 4, "title": "second", "update_time": 20.0},
            {"_1": 3, "title": "first", "update_time": 20.0},
        ]
        result = find_conversation([table])
        self.assertEqual(result, reference_find_conversation([table]))
        self.assertEqual(result["title"], "first")
        self.assertEqual(result["_candidate_item"], 6)

    def test_best_candidate_across_multiple_tables(self):
        left = sample_table(70, 12)
        right = sample_table(130, 24)
        right[-1]["update_time"] = 101.0
        self.assertEqual(
            find_conversation([left, right]),
            reference_find_conversation([left, right]),
        )
        self.assertEqual(find_conversation([left, right])["_candidate_table"], 1)

    def test_many_repeated_key_indices_have_identical_selection(self):
        for size, markers in ((70, 1), (200, 20), (1000, 90)):
            with self.subTest(size=size, markers=markers):
                table = sample_table(size, markers)
                self.assertEqual(
                    find_conversation([table]),
                    reference_find_conversation([table]),
                )

    def test_missing_or_empty_linear_values_keep_parse_error(self):
        for table in (["noise", {}], ["linear_conversation", {"_0": -1}]):
            with self.subTest(table=table):
                with self.assertRaises(ParseError):
                    find_conversation([table])
