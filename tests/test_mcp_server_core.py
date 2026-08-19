import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from portable_ai_context.cli import main as cli_main
from portable_ai_context.errors import PortableAIContextError
from portable_ai_context.mcp_server import create_mcp_server, run_mcp_stdio


class MCPServerCoreTests(unittest.TestCase):
    def test_missing_optional_dependency_has_content_safe_install_hint(self):
        with tempfile.TemporaryDirectory() as td:
            with mock.patch(
                "portable_ai_context.mcp_server.importlib.import_module",
                side_effect=ModuleNotFoundError("PRIVATE_MCP_IMPORT_DETAIL"),
            ):
                with self.assertRaises(PortableAIContextError) as caught:
                    create_mcp_server(td)
        self.assertEqual(
            str(caught.exception),
            "MCP server support is unavailable; install portable-ai-context[mcp]",
        )
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_stdio_runner_passes_explicit_transport(self):
        class FakeServer:
            def __init__(self):
                self.calls = []

            def run(self, *, transport):
                self.calls.append(transport)

        fake = FakeServer()
        with mock.patch(
            "portable_ai_context.mcp_server.create_mcp_server",
            return_value=fake,
        ) as create:
            run_mcp_stdio("PRIVATE_ROOT_VALUE")

        create.assert_called_once_with("PRIVATE_ROOT_VALUE")
        self.assertEqual(fake.calls, ["stdio"])

    def test_cli_mcp_forwards_root_without_stdout_banner(self):
        with tempfile.TemporaryDirectory() as td:
            stdout = io.StringIO()
            with mock.patch("portable_ai_context.cli.run_mcp_stdio") as run:
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["mcp", "--root", td])
        self.assertEqual(code, 0)
        run.assert_called_once_with(td)
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
