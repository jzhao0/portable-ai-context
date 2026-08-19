import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import urllib.error

from portable_ai_context.cli import main as cli_main
from portable_ai_context.compiler import (
    DEFAULT_GEMINI_API_BASE,
    DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
    BackendConfig,
    GeminiBackend,
    available_backends,
    create_backend,
)
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


def _response_body(*, finish_reason="STOP", parts=None, candidates=None, prompt_feedback=None):
    if candidates is None:
        if parts is None:
            parts = [{"text": "SAFE RESULT"}]
        candidates = [
            {
                "content": {"role": "model", "parts": parts},
                "finishReason": finish_reason,
                "index": 0,
            }
        ]
    value = {"candidates": candidates}
    if prompt_feedback is not None:
        value["promptFeedback"] = prompt_feedback
    return json.dumps(value).encode("utf-8")


class GeminiBackendTransportTests(unittest.TestCase):
    def setUp(self):
        self.api_key = "PRIVATE_GEMINI_KEY_VALUE"
        self.api_base = "https://private-gemini.example/v1beta"
        self.system = "PRIVATE_SYSTEM_PROMPT_CONTENT"
        self.user = "PRIVATE_USER_PROMPT_CONTENT"
        self.backend = GeminiBackend(
            api_key=self.api_key,
            api_base=self.api_base,
            max_output_tokens=777,
            timeout=19,
        )

    def _complete(self, model="gemini-test-model"):
        return self.backend.complete(
            model=model,
            system=self.system,
            user=self.user,
            stage="map",
        )

    def _assert_content_safe(self, message, *extra_private_values):
        for value in (
            self.api_key,
            self.api_base,
            self.system,
            self.user,
            *extra_private_values,
        ):
            self.assertNotIn(value, message)

    def test_request_matches_generate_content_contract(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response(_response_body())

        with mock.patch(
            "portable_ai_context.compiler.gemini.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            result = self._complete()

        self.assertEqual(result, "SAFE RESULT")
        request = captured["request"]
        self.assertEqual(
            request.full_url,
            self.api_base + "/models/gemini-test-model:generateContent",
        )
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(captured["timeout"], 19)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["x-goog-api-key"], self.api_key)

        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(
            payload["systemInstruction"],
            {"parts": [{"text": self.system}]},
        )
        self.assertEqual(
            payload["contents"],
            [{"role": "user", "parts": [{"text": self.user}]}],
        )
        self.assertEqual(
            payload["generationConfig"],
            {
                "candidateCount": 1,
                "maxOutputTokens": 777,
                "temperature": 0.1,
                "responseMimeType": "text/plain",
            },
        )
        self.assertNotIn("stage", payload)
        self.assertNotIn("tools", payload)
        self.assertNotIn("thinkingConfig", payload)

    def test_model_path_normalizes_exactly_one_models_prefix(self):
        self.assertEqual(
            self.backend._generate_url("gemini-safe_1.2"),
            self.api_base + "/models/gemini-safe_1.2:generateContent",
        )
        self.assertEqual(
            self.backend._generate_url("models/gemini-safe_1.2"),
            self.api_base + "/models/gemini-safe_1.2:generateContent",
        )

    def test_unsafe_model_path_is_rejected_without_echo(self):
        private_model = "models/../../PRIVATE_MODEL?key=PRIVATE_QUERY"
        with self.assertRaises(CompilerError) as caught:
            self._complete(private_model)
        self.assertEqual(str(caught.exception), "gemini backend model identifier is invalid")
        self.assertNotIn("PRIVATE_MODEL", str(caught.exception))
        self.assertNotIn("PRIVATE_QUERY", str(caught.exception))

    def test_multiple_final_text_parts_are_joined_and_thoughts_ignored(self):
        private_thought = "PRIVATE_THOUGHT_SUMMARY"
        private_signature = "PRIVATE_THOUGHT_SIGNATURE"
        body = _response_body(
            parts=[
                {"text": "first"},
                {"text": private_thought, "thought": True},
                {"functionCall": {"name": "PRIVATE_TOOL_NAME"}},
                {"text": "second", "thoughtSignature": private_signature},
            ]
        )
        with mock.patch(
            "portable_ai_context.compiler.gemini.urllib.request.urlopen",
            return_value=_Response(body),
        ):
            result = self._complete()
        self.assertEqual(result, "first\nsecond")
        self.assertNotIn(private_thought, result)
        self.assertNotIn(private_signature, result)
        self.assertNotIn("PRIVATE_TOOL_NAME", result)

    def test_max_tokens_is_explicit_truncation_failure(self):
        private_finish_message = "PRIVATE_FINISH_MESSAGE"
        body = json.dumps(
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "PRIVATE_PARTIAL_TEXT"}]},
                        "finishReason": "MAX_TOKENS",
                        "finishMessage": private_finish_message,
                    }
                ]
            }
        ).encode("utf-8")
        with mock.patch(
            "portable_ai_context.compiler.gemini.urllib.request.urlopen",
            return_value=_Response(body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "gemini backend output reached maxOutputTokens")
        self._assert_content_safe(
            str(caught.exception), private_finish_message, "PRIVATE_PARTIAL_TEXT"
        )

    def test_current_blocked_finish_reasons_fail_closed_without_echo(self):
        blocked = (
            "SAFETY",
            "RECITATION",
            "LANGUAGE",
            "BLOCKLIST",
            "PROHIBITED_CONTENT",
            "SPII",
            "IMAGE_SAFETY",
            "IMAGE_PROHIBITED_CONTENT",
            "IMAGE_OTHER",
            "NO_IMAGE",
            "IMAGE_RECITATION",
            "ESCALATION",
        )
        for finish_reason in blocked:
            with self.subTest(finish_reason=finish_reason):
                with mock.patch(
                    "portable_ai_context.compiler.gemini.urllib.request.urlopen",
                    return_value=_Response(
                        _response_body(
                            finish_reason=finish_reason,
                            parts=[{"text": "PRIVATE_BLOCKED_TEXT"}],
                        )
                    ),
                ):
                    with self.assertRaises(CompilerError) as caught:
                        self._complete()
                self.assertEqual(str(caught.exception), "gemini backend candidate was blocked")
                self.assertNotIn("PRIVATE_BLOCKED_TEXT", str(caught.exception))

    def test_non_text_or_incomplete_finish_reasons_fail_closed(self):
        reasons = (
            "MALFORMED_FUNCTION_CALL",
            "UNEXPECTED_TOOL_CALL",
            "TOO_MANY_TOOL_CALLS",
            "MISSING_THOUGHT_SIGNATURE",
            "MALFORMED_RESPONSE",
        )
        for finish_reason in reasons:
            with self.subTest(finish_reason=finish_reason):
                with mock.patch(
                    "portable_ai_context.compiler.gemini.urllib.request.urlopen",
                    return_value=_Response(_response_body(finish_reason=finish_reason)),
                ):
                    with self.assertRaises(CompilerError) as caught:
                        self._complete()
                self.assertEqual(
                    str(caught.exception),
                    "gemini backend returned a non-text or incomplete result",
                )

    def test_unspecified_other_and_unknown_finish_reasons_are_not_echoed(self):
        for finish_reason in (
            "FINISH_REASON_UNSPECIFIED",
            "OTHER",
            "PRIVATE_FUTURE_FINISH_REASON",
        ):
            with self.subTest(finish_reason=finish_reason):
                with mock.patch(
                    "portable_ai_context.compiler.gemini.urllib.request.urlopen",
                    return_value=_Response(_response_body(finish_reason=finish_reason)),
                ):
                    with self.assertRaises(CompilerError) as caught:
                        self._complete()
                self.assertEqual(
                    str(caught.exception),
                    "gemini backend returned an unsupported finish reason",
                )
                self.assertNotIn(finish_reason, str(caught.exception))

    def test_prompt_feedback_block_without_candidates_is_generic(self):
        private_reason = "PRIVATE_BLOCK_REASON"
        private_message = "PRIVATE_PROVIDER_BLOCK_DETAIL"
        body = json.dumps(
            {
                "promptFeedback": {
                    "blockReason": private_reason,
                    "blockReasonMessage": private_message,
                }
            }
        ).encode("utf-8")
        with mock.patch(
            "portable_ai_context.compiler.gemini.urllib.request.urlopen",
            return_value=_Response(body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "gemini backend prompt was blocked")
        self.assertNotIn(private_reason, str(caught.exception))
        self.assertNotIn(private_message, str(caught.exception))

    def test_no_candidate_without_block_feedback_is_distinct(self):
        with mock.patch(
            "portable_ai_context.compiler.gemini.urllib.request.urlopen",
            return_value=_Response(json.dumps({"candidates": []}).encode("utf-8")),
        ):
            with self.assertRaisesRegex(CompilerError, "returned no candidate"):
                self._complete()

    def test_candidate_cardinality_and_response_shape_fail_cleanly(self):
        bodies = [
            json.dumps([]).encode("utf-8"),
            json.dumps({"candidates": {"private": "value"}}).encode("utf-8"),
            _response_body(candidates=[{}, {}]),
            _response_body(candidates=["PRIVATE_CANDIDATE"]),
            _response_body(candidates=[{"finishReason": "STOP", "content": "PRIVATE"}]),
            _response_body(candidates=[{"finishReason": "STOP", "content": {"parts": "PRIVATE"}}]),
        ]
        for body in bodies:
            with self.subTest(body=body[:30]):
                with mock.patch(
                    "portable_ai_context.compiler.gemini.urllib.request.urlopen",
                    return_value=_Response(body),
                ):
                    with self.assertRaises(CompilerError) as caught:
                        self._complete()
                self.assertIn(
                    str(caught.exception),
                    {
                        "unexpected Gemini response shape",
                        "gemini backend returned no candidate",
                    },
                )
                self.assertNotIn("PRIVATE", str(caught.exception))

    def test_success_without_final_text_fails_without_echoing_non_text_payload(self):
        private_tool = "PRIVATE_TOOL_PAYLOAD"
        body = _response_body(
            parts=[
                {"text": "PRIVATE_THOUGHT", "thought": True},
                {"functionCall": {"name": private_tool}},
            ]
        )
        with mock.patch(
            "portable_ai_context.compiler.gemini.urllib.request.urlopen",
            return_value=_Response(body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "gemini backend returned no text content")
        self.assertNotIn(private_tool, str(caught.exception))
        self.assertNotIn("PRIVATE_THOUGHT", str(caught.exception))

    def test_invalid_json_does_not_echo_response_body(self):
        private_body = b"PRIVATE_INVALID_GEMINI_JSON {"
        with mock.patch(
            "portable_ai_context.compiler.gemini.urllib.request.urlopen",
            return_value=_Response(private_body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "gemini backend returned invalid JSON")
        self._assert_content_safe(str(caught.exception), private_body.decode("utf-8"))

    def test_http_error_reports_only_status(self):
        private_body = "PRIVATE_GEMINI_ERROR_BODY"
        error = urllib.error.HTTPError(
            url=self.api_base + "/models/private:generateContent",
            code=429,
            msg="PRIVATE_HTTP_REASON",
            hdrs=None,
            fp=io.BytesIO(private_body.encode("utf-8")),
        )
        with mock.patch(
            "portable_ai_context.compiler.gemini.urllib.request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "gemini backend HTTP status 429")
        self._assert_content_safe(str(caught.exception), private_body, "PRIVATE_HTTP_REASON")
        self.assertIs(caught.exception.__cause__, error)

    def test_transport_error_is_generic(self):
        private_reason = "PRIVATE_GEMINI_TRANSPORT_DETAIL"
        error = urllib.error.URLError(private_reason)
        with mock.patch(
            "portable_ai_context.compiler.gemini.urllib.request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "gemini backend transport failed")
        self._assert_content_safe(str(caught.exception), private_reason)
        self.assertIs(caught.exception.__cause__, error)


class GeminiBackendRegistryTests(unittest.TestCase):
    def test_gemini_is_registered_with_safe_defaults(self):
        self.assertIn("gemini", available_backends())
        backend = create_backend(
            "gemini",
            BackendConfig(
                api_key_env="GEMINI_API_KEY",
                environment={"GEMINI_API_KEY": "PRIVATE_KEY"},
            ),
        )
        self.assertIsInstance(backend, GeminiBackend)
        self.assertEqual(backend.api_base, DEFAULT_GEMINI_API_BASE)
        self.assertEqual(backend.max_output_tokens, DEFAULT_GEMINI_MAX_OUTPUT_TOKENS)

    def test_factory_accepts_custom_base_max_output_tokens_and_timeout(self):
        backend = create_backend(
            "gemini",
            BackendConfig(
                api_base="https://gateway.example/gemini/v1beta",
                api_key_env="CUSTOM_KEY",
                timeout=23,
                environment={"CUSTOM_KEY": "PRIVATE_KEY"},
                options={"gemini_max_output_tokens": 1234},
            ),
        )
        self.assertEqual(backend.api_base, "https://gateway.example/gemini/v1beta")
        self.assertEqual(backend.max_output_tokens, 1234)
        self.assertEqual(backend.timeout, 23)

    def test_factory_rejects_invalid_max_output_tokens(self):
        for value in (0, -1, True, "4096"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    CompilerError, "maxOutputTokens must be a positive integer"
                ):
                    create_backend(
                        "gemini",
                        BackendConfig(
                            environment={"PAIC_API_KEY": "PRIVATE_KEY"},
                            options={"gemini_max_output_tokens": value},
                        ),
                    )


class _RecordingBackend:
    def complete(self, *, model, system, user, stage):
        return "safe compiled output"


class GeminiBackendCliTests(unittest.TestCase):
    def test_cli_forwards_gemini_max_output_tokens_through_backend_options(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "source.jsonl"
            source.write_text(
                json.dumps({"role": "user", "text": "question"})
                + "\n"
                + json.dumps({"role": "assistant", "text": "answer"})
                + "\n",
                encoding="utf-8",
            )
            out = root / "out"
            backend = _RecordingBackend()
            with mock.patch("portable_ai_context.cli.create_backend", return_value=backend) as create:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = cli_main(
                        [
                            "compile",
                            str(source),
                            "-o",
                            str(out),
                            "--backend",
                            "gemini",
                            "--api-key-env",
                            "GEMINI_API_KEY",
                            "--gemini-max-output-tokens",
                            "7777",
                            "--map-model",
                            "map-model",
                            "--final-model",
                            "final-model",
                        ]
                    )
        self.assertEqual(code, 0)
        backend_name, config = create.call_args.args
        self.assertEqual(backend_name, "gemini")
        self.assertEqual(config.api_key_env, "GEMINI_API_KEY")
        self.assertEqual(config.options["gemini_max_output_tokens"], 7777)
        self.assertIs(config.environment, os.environ)


if __name__ == "__main__":
    unittest.main()
