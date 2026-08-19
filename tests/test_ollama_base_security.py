import unittest

from portable_ai_context.compiler import OllamaBackend
from portable_ai_context.errors import CompilerError


class OllamaApiBaseSecurityTests(unittest.TestCase):
    def test_ipv6_localhost_base_is_supported(self):
        backend = OllamaBackend(api_base="http://[::1]:11434")
        self.assertEqual(backend.chat_url, "http://[::1]:11434/api/chat")

    def test_malformed_authority_and_ports_fail_closed(self):
        unsafe = (
            r"http://local\host:11434",
            r"http://localhost:11434\@PRIVATE_HOST",
            "http://localhost:PRIVATE_PORT",
            "http://localhost:99999",
            "http://[::1",
        )
        for base in unsafe:
            with self.subTest(base=base):
                with self.assertRaises(CompilerError) as caught:
                    OllamaBackend(api_base=base)
                self.assertEqual(
                    str(caught.exception),
                    "ollama backend API base is invalid",
                )
                self.assertNotIn("PRIVATE", str(caught.exception))

    def test_control_whitespace_and_encoded_traversal_fail_closed(self):
        unsafe = (
            "http://local\nhost:11434",
            "http://localhost:11434/PRIVATE%00PATH",
            "http://localhost:11434/PRIVATE%09PATH",
            "http://localhost:11434/%252e%252e/PRIVATE_PATH",
            "http://localhost:11434/%255cPRIVATE_PATH",
        )
        for base in unsafe:
            with self.subTest(base=base):
                with self.assertRaises(CompilerError) as caught:
                    OllamaBackend(api_base=base)
                self.assertEqual(
                    str(caught.exception),
                    "ollama backend API base is invalid",
                )
                self.assertNotIn("PRIVATE", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
