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
    ANTHROPIC_API_VERSION,
    DEFAULT_ANTHROPIC_API_BASE,
    DEFAULT_ANTHROPIC_MAX_TOKENS,
    AnthropicBackend,
    BackendConfig,
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


def _message_body(*, stop_reason="end_turn", content=None) -> bytes:
    if content is None:
        content = [{"type": "text", "text": "SAFE RESULT"}]
    return json.dumps(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "content": content,
            "model": "test-model",
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    ).encode("utf-8")


class AnthropicBackendTransportTests(unittest.TestCase):
    def setUp(self):
        self.api_key = "PRIVATE_ANTHROPIC_KEY_VALUE"
        self.api_base = "https://private-anthropic.example"
        self.system = "PRIVATE_SYSTEM_PROMPT_CONTENT"
        self.user = "PRIVATE_USER_PROMPT_CONTENT"
        self.backend = AnthropicBackend(
            api_key=self.api_key,
            api_base=self.api_base,
            max_tokens=777,
            timeout=19,
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

    def test_request_matches_messages_api_contract(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response(_message_body())

        with mock.patch(
            "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            result = self._complete()

        self.assertEqual(result, "SAFE RESULT")
        request = captured["request"]
        self.assertEqual(request.full_url, self.api_base + "/v1/messages")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(captured["timeout"], 19)

        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["x-api-key"], self.api_key)
        self.assertEqual(headers["anthropic-version"], ANTHROPIC_API_VERSION)

        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "private-model-name")
        self.assertEqual(payload["max_tokens"], 777)
        self.assertEqual(payload["system"], self.system)
        self.assertEqual(
            payload["messages"],
            [{"role": "user", "content": self.user}],
        )
        self.assertIs(payload["stream"], False)
        self.assertNotIn("stage", payload)

    def test_api_base_normalization_accepts_host_or_v1_base(self):
        host = AnthropicBackend(api_key="x", api_base="https://api.example.test")
        versioned = AnthropicBackend(api_key="x", api_base="https://api.example.test/v1/")
        self.assertEqual(host._messages_url(), "https://api.example.test/v1/messages")
        self.assertEqual(versioned._messages_url(), "https://api.example.test/v1/messages")

    def test_multiple_text_blocks_are_joined_and_non_text_blocks_ignored(self):
        body = _message_body(
            content=[
                {"type": "text", "text": "first"},
                {"type": "thinking", "thinking": "PRIVATE_THINKING_CONTENT"},
                {"type": "text", "text": "second"},
            ]
        )
        with mock.patch(
            "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
            return_value=_Response(body),
        ):
            result = self._complete()
        self.assertEqual(result, "first\nsecond")
        self.assertNotIn("PRIVATE_THINKING_CONTENT", result)

    def test_incomplete_stop_reasons_fail_closed(self):
        expected = {
            "max_tokens": "anthropic backend output reached max_tokens",
            "refusal": "anthropic backend returned a refusal",
            "model_context_window_exceeded": "anthropic backend exceeded the model context window",
            "tool_use": "anthropic backend returned an unexpected tool-use result",
            "pause_turn": "anthropic backend returned an incomplete paused result",
        }
        for stop_reason, expected_message in expected.items():
            with self.subTest(stop_reason=stop_reason):
                body = _message_body(
                    stop_reason=stop_reason,
                    content=[{"type": "text", "text": "PRIVATE_INCOMPLETE_TEXT"}],
                )
                with mock.patch(
                    "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
                    return_value=_Response(body),
                ):
                    with self.assertRaises(CompilerError) as caught:
                        self._complete()
                self.assertEqual(str(caught.exception), expected_message)
                self._assert_content_safe(str(caught.exception), "PRIVATE_INCOMPLETE_TEXT")

    def test_unknown_stop_reason_is_not_echoed(self):
        private_reason = "PRIVATE_FUTURE_STOP_REASON"
        with mock.patch(
            "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
            return_value=_Response(_message_body(stop_reason=private_reason)),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(
            str(caught.exception),
            "anthropic backend returned an unsupported stop reason",
        )
        self.assertNotIn(private_reason, str(caught.exception))

    def test_success_without_text_blocks_fails_without_echoing_non_text_content(self):
        private_thinking = "PRIVATE_THINKING_CONTENT"
        body = _message_body(
            content=[{"type": "thinking", "thinking": private_thinking}]
        )
        with mock.patch(
            "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
            return_value=_Response(body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "anthropic backend returned no text content")
        self.assertNotIn(private_thinking, str(caught.exception))

    def test_malformed_text_block_and_response_shape_fail_cleanly(self):
        bodies = [
            _message_body(content=[{"type": "text", "text": 123}]),
            json.dumps({"content": "PRIVATE_CONTENT", "stop_reason": "end_turn"}).encode("utf-8"),
            json.dumps(["PRIVATE_ARRAY_PAYLOAD"]).encode("utf-8"),
        ]
        for body in bodies:
            with self.subTest(body=body[:30]):
                with mock.patch(
                    "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
                    return_value=_Response(body),
                ):
                    with self.assertRaises(CompilerError) as caught:
                        self._complete()
                self.assertEqual(str(caught.exception), "unexpected Anthropic response shape")
                self._assert_content_safe(str(caught.exception), "PRIVATE_CONTENT", "PRIVATE_ARRAY_PAYLOAD")

    def test_invalid_json_does_not_echo_response_body(self):
        private_body = b"PRIVATE_INVALID_ANTHROPIC_JSON {"
        with mock.patch(
            "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
            return_value=_Response(private_body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "anthropic backend returned invalid JSON")
        self._assert_content_safe(str(caught.exception), private_body.decode("utf-8"))

    def test_http_error_reports_only_status(self):
        private_body = "PRIVATE_ANTHROPIC_ERROR_BODY"
        error = urllib.error.HTTPError(
            url=self.api_base + "/v1/messages",
            code=429,
            msg="PRIVATE_HTTP_REASON",
            hdrs=None,
            fp=io.BytesIO(private_body.encode("utf-8")),
        )
        with mock.patch(
            "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "anthropic backend HTTP status 429")
        self._assert_content_safe(str(caught.exception), private_body, "PRIVATE_HTTP_REASON")
        self.assertIs(caught.exception.__cause__, error)

    def test_transport_error_is_generic(self):
        private_reason = "PRIVATE_ANTHROPIC_TRANSPORT_DETAIL"
        error = urllib.error.URLError(private_reason)
        with mock.patch(
            "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "anthropic backend transport failed")
        self._assert_content_safe(str(caught.exception), private_reason)
        self.assertIs(caught.exception.__cause__, error)


class AnthropicBackendRegistryTests(unittest.TestCase):
    def test_anthropic_is_registered_with_safe_defaults(self):
        self.assertIn("anthropic", available_backends())
        backend = create_backend(
            "anthropic",
            BackendConfig(
                api_key_env="ANTHROPIC_API_KEY",
                environment={"ANTHROPIC_API_KEY": "PRIVATE_KEY"},
            ),
        )
        self.assertIsInstance(backend, AnthropicBackend)
        self.assertEqual(backend.api_base, DEFAULT_ANTHROPIC_API_BASE)
        self.assertEqual(backend.max_tokens, DEFAULT_ANTHROPIC_MAX_TOKENS)

    def test_factory_accepts_custom_base_and_max_tokens(self):
        backend = create_backend(
            "anthropic",
            BackendConfig(
                api_base="https://gateway.example/anthropic/v1",
                api_key_env="CUSTOM_KEY",
                timeout=23,
                environment={"CUSTOM_KEY": "PRIVATE_KEY"},
                options={"anthropic_max_tokens": 1234},
            ),
        )
        self.assertEqual(backend.api_base, "https://gateway.example/anthropic/v1")
        self.assertEqual(backend._messages_url(), "https://gateway.example/anthropic/v1/messages")
        self.assertEqual(backend.max_tokens, 1234)
        self.assertEqual(backend.timeout, 23)

    def test_factory_rejects_invalid_max_tokens(self):
        for value in (0, -1, True, "4096"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(CompilerError, "max_tokens must be a positive integer"):
                    create_backend(
                        "anthropic",
                        BackendConfig(
                            environment={"PAIC_API_KEY": "PRIVATE_KEY"},
                            options={"anthropic_max_tokens": value},
                        ),
                    )


class _RecordingBackend:
    def complete(self, *, model, system, user, stage):
        return "safe compiled output"


class AnthropicBackendCliTests(unittest.TestCase):
    def test_cli_forwards_anthropic_max_tokens_through_backend_options(self):
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
                            "anthropic",
                            "--api-key-env",
                            "ANTHROPIC_API_KEY",
                            "--anthropic-max-tokens",
                            "7777",
                            "--map-model",
                            "map-model",
                            "--final-model",
                            "final-model",
                        ]
                    )
        self.assertEqual(code, 0)
        backend_name, config = create.call_args.args
        self.assertEqual(backend_name, "anthropic")
        self.assertEqual(config.api_key_env, "ANTHROPIC_API_KEY")
        self.assertEqual(config.options["anthropic_max_tokens"], 7777)
        self.assertIs(config.environment, os.environ)


if __name__ == "__main__":
    unittest.main()
