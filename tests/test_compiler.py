import tempfile
from pathlib import Path
import unittest

from portable_ai_context.compiler.pipeline import compile_migration
from _helpers import sample_conversation


class FakeBackend:
    def __init__(self):
        self.calls = []

    def complete(self, *, model, system, user, stage):
        self.calls.append((model, stage, user))
        if stage == "map":
            return "VERIFIED: synthetic checkpoint"
        if stage == "merge":
            return "MERGED: synthetic checkpoint"
        return "FINAL MIGRATION PROMPT"


class CompilerTests(unittest.TestCase):
    def test_compile_without_network(self):
        backend = FakeBackend()
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "state.json"
            final, notes = compile_migration(
                sample_conversation(),
                backend=backend,
                map_model="fast",
                final_model="strong",
                chunk_chars=40,
                reduce_chars=10000,
                state_path=state,
            )
            self.assertEqual(final, "FINAL MIGRATION PROMPT")
            self.assertTrue(notes)
            self.assertTrue(state.exists())
            self.assertEqual(backend.calls[-1][1], "final")


if __name__ == "__main__":
    unittest.main()
