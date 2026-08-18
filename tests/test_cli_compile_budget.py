import unittest

from portable_ai_context.cli import build_parser


BASE = [
    "compile",
    "conversation.jsonl",
    "-o",
    "out",
    "--api-base",
    "https://api.example.invalid/v1",
    "--map-model",
    "fast",
    "--final-model",
    "strong",
]


class CompileBudgetCliTests(unittest.TestCase):
    def test_explicit_budget_parses(self):
        args = build_parser().parse_args(BASE + ["--budget", "12000"])
        self.assertEqual(args.budget, 12000)
        self.assertIsNone(args.profile)

    def test_named_profile_parses(self):
        args = build_parser().parse_args(BASE + ["--profile", "standard"])
        self.assertEqual(args.profile, "standard")
        self.assertIsNone(args.budget)

    def test_budget_and_profile_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(BASE + ["--budget", "12000", "--profile", "lite"])

    def test_non_positive_budget_is_rejected(self):
        with self.assertRaises(SystemExit):
            build_parser().parse_args(BASE + ["--budget", "0"])


if __name__ == "__main__":
    unittest.main()
