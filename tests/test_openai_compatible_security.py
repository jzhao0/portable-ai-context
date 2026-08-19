import io
import json
import unittest
from unittest import mock
import urllib.error

from portable_ai_context.compiler import OpenAICompatibleBackend
from portable_ai_context.errors import CompilerError


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class OpenAICompatibleSecurityTests(unittest.TestCase):
    def setUp(self):
        self.api_key = "PRIVATE_API_KEY_VALUE"
        self.api_base = "https://private-provider.example/v1"
        self.system = "PRIVATE_SYSTEM_PROMPT_CONTENT"
        self.user = "PRIVATE_USER_PROMPT_CONTENT"
        self.backend = OpenAICompatibleBackend(
            api_base=self.api_base,
            api_key=self.api_key,
            timeout=9,
        )

    def _complete(self):
        return self.backend.complete(
            model="private-model-name",
            system=self.system,
            user=self.user,
            stage="map",
        )

    def _assert_content_safe(self, message: str, *extra_private_values: str):
        for value in (
            self.api_key,
            self.api_base,
            self.system,
            self.user,
            *extra_private_values,
        ):
            self.assertNotIn(value, message)

    def test_http_error_reports_only_status_without_body_or_request_content(self):
        private_body = "PRIVATE_PROVIDER_ERROR_BODY_WITH_ECHOED_PROMPT"
        error = urllib.error.HTTPError(
            url=self.api_base + "/chat/completions",
            code=429,
            msg="PRIVATE_HTTP_REASON",
            hdrs=None,
            fp=io.BytesIO(private_body.encode("utf-8")),
        )
        with mock.patch(
            "portable_ai_context.compiler.openai_compatible.urllib.request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "compiler backend HTTP status 429")
        self._assert_content_safe(str(caught.exception), private_body, "PRIVATE_HTTP_REASON")
        self.assertIs(caught.exception.__cause__, error)

    def test_transport_error_is_generic_and_keeps_detail_only_in_exception_chain(self):
        private_reason = "PRIVATE_TRANSPORT_DETAIL"
        error = urllib.error.URLError(private_reason)
        with mock.patch(
            "portable_ai_context.compiler.openai_compatible.urllib.request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "compiler backend transport failed")
        self._assert_content_safe(str(caught.exception), private_reason)
        self.assertIs(caught.exception.__cause__, error)

    def test_invalid_json_does_not_echo_response_body(self):
        private_body = b"PRIVATE_INVALID_JSON_BODY {"
        with mock.patch(
            "portable_ai_context.compiler.openai_compatible.urllib.request.urlopen",
            return_value=_Response(private_body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "compiler backend returned invalid JSON")
        self._assert_content_safe(str(caught.exception), private_body.decode("utf-8"))

    def test_unexpected_response_shape_does_not_echo_provider_payload(self):
        private_value = "PRIVATE_PROVIDER_PAYLOAD_VALUE"
        body = json.dumps({"error": {"detail": private_value}}).encode("utf-8")
        with mock.patch(
            "portable_ai_context.compiler.openai_compatible.urllib.request.urlopen",
            return_value=_Response(body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "unexpected OpenAI-compatible response shape")
        self._assert_content_safe(str(caught.exception), private_value)

    def test_empty_content_uses_generic_error(self):
        body = json.dumps(
            {"choices": [{"message": {"content": "   "}}]}
        ).encode("utf-8")
        with mock.patch(
            "portable_ai_context.compiler.openai_compatible.urllib.request.urlopen",
            return_value=_Response(body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "compiler returned empty content")
        self._assert_content_safe(str(caught.exception))

    def test_success_path_still_strips_content(self):
        body = json.dumps(
            {"choices": [{"message": {"content": "  SAFE RESULT  "}}]}
        ).encode("utf-8")
        with mock.patch(
            "portable_ai_context.compiler.openai_compatible.urllib.request.urlopen",
            return_value=_Response(body),
        ):
            result = self._complete()
        self.assertEqual(result, "SAFE RESULT")


if __name__ == "__main__":
    unittest.main()
