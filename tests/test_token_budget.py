import unittest

from portable_ai_context.compiler import CharacterTokenCounter, CallableTokenCounter, PROFILE_BUDGETS


class TokenBudgetTests(unittest.TestCase):
    def test_character_counter_is_dependency_free_estimate(self):
        counter = CharacterTokenCounter(chars_per_token=4.0)
        self.assertFalse(counter.exact)
        self.assertEqual(counter.name, "character_estimate")
        self.assertEqual(counter.count(""), 0)
        self.assertEqual(counter.count("12345"), 2)

    def test_callable_counter_can_represent_exact_target_tokenizer(self):
        counter = CallableTokenCounter(
            fn=lambda text: len(text.split()),
            name="deterministic-test-tokenizer",
            exact=True,
        )
        self.assertTrue(counter.exact)
        self.assertEqual(counter.count("one two three"), 3)

    def test_profile_budgets_are_stable_alpha_contract(self):
        self.assertEqual(
            PROFILE_BUDGETS,
            {"lite": 4000, "standard": 16000, "full": 64000},
        )


if __name__ == "__main__":
    unittest.main()
