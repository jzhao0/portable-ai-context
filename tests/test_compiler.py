import tempfile
from pathlib import Path
import unittest

from portable_ai_context.compiler import CallableTokenCounter, PROFILE_BUDGETS
from portable_ai_context.compiler.pipeline import compile_migration
from _helpers import sample_conversation


class FakeBackend:
    def __init__(self, *, final="FINAL MIGRATION PROMPT", budget="REDUCED NEXT ACTION"):
        self.calls = []
        self.final = final
        self.budget = budget

    def complete(self, *, model, system, user, stage):
        self.calls.append({"model": model, "stage": stage, "system": system, "user": user})
        if stage == "map":
            return "VERIFIED: synthetic checkpoint"
        if stage == "merge":
            return "MERGED: synthetic checkpoint"
        if stage == "budget":
            return self.budget
        return self.final


def exact_words():
    return CallableTokenCounter(
        fn=lambda text: len(text.split()),
        name="fake_exact_words",
        exact=True,
    )


class CompilerTests(unittest.TestCase):
    def test_compile_without_network_preserves_two_value_unpacking(self):
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            result = compile_migration(
                sample_conversation(),
                backend=backend,
                map_model="fast",
                final_model="strong",
                chunk_chars=40,
                reduce_chars=10000,
                state_path=state,
            )
            final, notes = result
            self.assertEqual(final, "FINAL MIGRATION PROMPT")
            self.assertTrue(notes)
            self.assertTrue(state.exists())
            self.assertEqual(backend.calls[-1]["stage"], "final")
            self.assertFalse(result.report.tokenizer_exact)
            self.assertIsNone(result.report.budget_tokens)
            self.assertIsNone(result.report.budget_met)

    def test_explicit_budget_uses_exact_counter_and_budget_reduction(self):
        backend = FakeBackend(
            final="one two three four five six seven eight",
            budget="breakpoint blocker next action",
        )
        result = compile_migration(
            sample_conversation(),
            backend=backend,
            map_model="fast",
            final_model="strong",
            chunk_chars=10000,
            reduce_chars=10000,
            budget_tokens=4,
            token_counter=exact_words(),
        )

        self.assertEqual(result.final, "breakpoint blocker next action")
        self.assertEqual([call["stage"] for call in backend.calls][-2:], ["final", "budget"])
        budget_call = backend.calls[-1]
        self.assertIn("current breakpoint", budget_call["system"])
        self.assertIn("exact next action", budget_call["system"])
        self.assertEqual(result.report.tokenizer, "fake_exact_words")
        self.assertTrue(result.report.tokenizer_exact)
        self.assertEqual(result.report.budget_tokens, 4)
        self.assertEqual(result.report.output_token_estimate, 4)
        self.assertEqual(result.report.budget_overrun_tokens, 0)
        self.assertTrue(result.report.budget_met)
        self.assertTrue(result.report.budget_reduction_applied)
        self.assertGreater(result.report.source_token_estimate, result.report.output_token_estimate)
        self.assertIsNotNone(result.report.compression_ratio)

    def test_budget_overrun_is_reported_not_silently_truncated(self):
        backend = FakeBackend(
            final="one two three four five",
            budget="still four tokens here",
        )
        result = compile_migration(
            sample_conversation(),
            backend=backend,
            map_model="fast",
            final_model="strong",
            budget_tokens=3,
            token_counter=exact_words(),
        )
        self.assertEqual(result.final, "still four tokens here")
        self.assertEqual(result.report.output_token_estimate, 4)
        self.assertEqual(result.report.budget_overrun_tokens, 1)
        self.assertFalse(result.report.budget_met)

    def test_named_profiles_resolve_to_documented_budgets(self):
        for profile, expected in PROFILE_BUDGETS.items():
            with self.subTest(profile=profile):
                backend = FakeBackend(final="compact")
                result = compile_migration(
                    sample_conversation(),
                    backend=backend,
                    map_model="fast",
                    final_model="strong",
                    profile=profile,
                    token_counter=exact_words(),
                )
                self.assertEqual(result.report.profile, profile)
                self.assertEqual(result.report.budget_tokens, expected)
                self.assertTrue(result.report.budget_met)
                self.assertIn(f"no more than {expected} tokens", backend.calls[-1]["user"])

    def test_budget_and_profile_are_mutually_exclusive_in_python_api(self):
        with self.assertRaisesRegex(ValueError, "mutually exclusive"):
            compile_migration(
                sample_conversation(),
                backend=FakeBackend(),
                map_model="fast",
                final_model="strong",
                budget_tokens=100,
                profile="lite",
            )


if __name__ == "__main__":
    unittest.main()
