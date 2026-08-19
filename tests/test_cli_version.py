import contextlib
import io
import unittest

from portable_ai_context import __version__
from portable_ai_context.cli import build_parser


class CliVersionTests(unittest.TestCase):
    def test_global_version_flag_reports_package_version(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            with self.assertRaises(SystemExit) as raised:
                build_parser().parse_args(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"paic {__version__}")


if __name__ == "__main__":
    unittest.main()
