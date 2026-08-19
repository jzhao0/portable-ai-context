from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest import mock
import urllib.error

from portable_ai_context.cli import _compile_token_counter, build_parser
from portable_ai_context.compiler import (
    ANTHROPIC_API_VERSION,
    AnthropicBackend,
    GeminiBackend,
    ProviderNativeTokenCounter,
    compile_migration,
)
from portable_ai_context.errors import CompilerError, PortableAIContextError
from tests._helpers import sample_conversation


class _Response:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class ProviderNativeTransportTests(unittest.TestCase):
    def test_anthropic_counter_uses_count_tokens_contract_and_is_estimated(self):
        api_key = "PRIVATE_ANTHROPIC_TOKEN_COUNTER_KEY"
        private_text = "PRIVATE_ANTHROPIC_TOKEN_COUNTER_INPUT"
        backend = AnthropicBackend(
            api_key=api_key,
            api_base="https://anthropic-counter.example/v1/",
            timeout=17,
        )
        counter = ProviderNativeTokenCounter(
            backend=backend,
            model="claude-test-model",
        )
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response(json.dumps({"input_tokens": 37}).encode("utf-8"))

        with mock.patch(
            "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            value = counter.count(private_text)

        self.assertEqual(value, 37)
        self.assertEqual(counter.name, "anthropic_count_tokens:claude-test-model")
        self.assertIs(counter.exact, False)
        request = captured["request"]
        self.assertEqual(
            request.full_url,
            "https://anthropic-counter.example/v1/messages/count_tokens",
        )
        self.assertEqual(captured["timeout"], 17)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["x-api-key"], api_key)
        self.assertEqual(headers["anthropic-version"], ANTHROPIC_API_VERSION)
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {
                "model": "claude-test-model",
                "messages": [{"role": "user", "content": private_text}],
            },
        )

    def test_gemini_counter_uses_count_tokens_contract_and_is_provider_exact(self):
        api_key = "PRIVATE_GEMINI_TOKEN_COUNTER_KEY"
        private_text = "PRIVATE_GEMINI_TOKEN_COUNTER_INPUT"
        backend = GeminiBackend(
            api_key=api_key,
            api_base="https://gemini-counter.example/v1beta/",
            timeout=23,
        )
        counter = ProviderNativeTokenCounter(
            backend=backend,
            model="models/gemini-test-model",
        )
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response(json.dumps({"totalTokens": 41}).encode("utf-8"))

        with mock.patch(
            "portable_ai_context.compiler.gemini.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            value = counter.count(private_text)

        self.assertEqual(value, 41)
        self.assertEqual(
            counter.name,
            "gemini_count_tokens:models/gemini-test-model",
        )
        self.assertIs(counter.exact, True)
        request = captured["request"]
        self.assertEqual(
            request.full_url,
            "https://gemini-counter.example/v1beta/models/gemini-test-model:countTokens",
        )
        self.assertEqual(captured["timeout"], 23)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["content-type"], "application/json")
        self.assertEqual(headers["x-goog-api-key"], api_key)
        self.assertEqual(
            json.loads(request.data.decode("utf-8")),
            {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": private_text}],
                    }
                ]
            },
        )

    def test_token_count_response_shapes_fail_closed(self):
        cases = [
            (
                AnthropicBackend(api_key="secret"),
                "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
                "claude-test",
                "input_tokens",
                "unexpected Anthropic token-count response shape",
            ),
            (
                GeminiBackend(api_key="secret"),
                "portable_ai_context.compiler.gemini.urllib.request.urlopen",
                "gemini-test",
                "totalTokens",
                "unexpected Gemini token-count response shape",
            ),
        ]
        invalid_values = (None, -1, True, "12", 1.5)
        private_text = "PRIVATE_SHOULD_NOT_APPEAR_IN_ERRORS"

        for backend, patch_target, model, field, expected in cases:
            counter = ProviderNativeTokenCounter(backend=backend, model=model)
            for invalid in invalid_values:
                with self.subTest(provider=counter.name, invalid=invalid):
                    body = {} if invalid is None else {field: invalid}
                    with mock.patch(
                        patch_target,
                        return_value=_Response(json.dumps(body).encode("utf-8")),
                    ):
                        with self.assertRaises(CompilerError) as caught:
                            counter.count(private_text)
                    self.assertEqual(str(caught.exception), expected)
                    self.assertNotIn(private_text, str(caught.exception))

    def test_invalid_json_and_http_errors_do_not_echo_private_inputs(self):
        private_text = "PRIVATE_NATIVE_COUNTER_BODY"
        private_remote_body = b"PRIVATE_PROVIDER_ERROR_BODY"
        backends = [
            (
                AnthropicBackend(api_key="secret"),
                "portable_ai_context.compiler.anthropic.urllib.request.urlopen",
                "claude-test",
                "anthropic token counter returned invalid JSON",
                "anthropic token counter HTTP status 429",
            ),
            (
                GeminiBackend(api_key="secret"),
                "portable_ai_context.compiler.gemini.urllib.request.urlopen",
                "gemini-test",
                "gemini token counter returned invalid JSON",
                "gemini token counter HTTP status 429",
            ),
        ]

        for backend, patch_target, model, invalid_expected, http_expected in backends:
            counter = ProviderNativeTokenCounter(backend=backend, model=model)
            with mock.patch(
                patch_target,
                return_value=_Response(private_remote_body),
            ):
                with self.assertRaises(CompilerError) as caught:
                    counter.count(private_text)
            self.assertEqual(str(caught.exception), invalid_expected)
            self.assertNotIn(private_text, str(caught.exception))
            self.assertNotIn(private_remote_body.decode(), str(caught.exception))

            http_error = urllib.error.HTTPError(
                url="https://private.example",
                code=429,
                msg="PRIVATE_REMOTE_REASON",
                hdrs=None,
                fp=None,
            )
            with mock.patch(patch_target, side_effect=http_error):
                with self.assertRaises(CompilerError) as caught:
                    counter.count(private_text)
            self.assertEqual(str(caught.exception), http_expected)
            self.assertNotIn(private_text, str(caught.exception))
            self.assertNotIn("PRIVATE_REMOTE_REASON", str(caught.exception))


class ProviderNativeAdapterAndCLITests(unittest.TestCase):
    @staticmethod
    def _args(*, token_counter: str, final_model: str = "model-test", tokenizer_model=None, tiktoken_encoding=None):
        return SimpleNamespace(
            token_counter=token_counter,
            final_model=final_model,
            tokenizer_model=tokenizer_model,
            tiktoken_encoding=tiktoken_encoding,
        )

    def test_provider_native_requires_supported_counting_backend(self):
        class UnsupportedBackend:
            def complete(self, *, model, system, user, stage):
                return "unused"

        with self.assertRaises(CompilerError) as caught:
            ProviderNativeTokenCounter(
                backend=UnsupportedBackend(),
                model="model-test",
            )
        self.assertEqual(
            str(caught.exception),
            "provider-native token counter requires an Anthropic or Gemini backend",
        )

    def test_cli_selection_reuses_backend_and_rejects_tiktoken_only_options(self):
        anthropic = AnthropicBackend(api_key="secret")
        selected = _compile_token_counter(
            self._args(token_counter="provider-native", final_model="claude-test"),
            anthropic,
        )
        self.assertIs(selected.backend, anthropic)
        self.assertEqual(selected.model, "claude-test")

        with self.assertRaises(PortableAIContextError) as caught:
            _compile_token_counter(
                self._args(
                    token_counter="provider-native",
                    tokenizer_model="tiktoken-only-model",
                ),
                anthropic,
            )
        self.assertEqual(
            str(caught.exception),
            "tiktoken tokenizer options require --token-counter tiktoken",
        )

    def test_character_default_remains_offline_and_requires_no_counting_backend(self):
        class NoCountingCapability:
            pass

        selected = _compile_token_counter(
            self._args(token_counter="character"),
            NoCountingCapability(),
        )
        self.assertIsNone(selected)

        args = build_parser().parse_args(
            [
                "compile",
                "source.jsonl",
                "-o",
                "out",
                "--api-base",
                "https://example.invalid/v1",
                "--map-model",
                "map",
                "--final-model",
                "final",
            ]
        )
        self.assertEqual(args.token_counter, "character")

    def test_compile_report_records_native_counter_semantics(self):
        class FakeGeminiCountingBackend:
            token_counter_provider = "gemini"
            token_counter_exact = True

            def count_input_tokens(self, *, model, text):
                self.last_count_model = model
                return len(text.encode("utf-8"))

            def complete(self, *, model, system, user, stage):
                return "SAFE FINAL" if stage in {"final", "budget"} else "SAFE NOTE"

        backend = FakeGeminiCountingBackend()
        counter = ProviderNativeTokenCounter(
            backend=backend,
            model="gemini-test",
        )
        result = compile_migration(
            sample_conversation(),
            backend=backend,
            map_model="map-test",
            final_model="gemini-test",
            token_counter=counter,
        )
        self.assertEqual(
            result.report.tokenizer,
            "gemini_count_tokens:gemini-test",
        )
        self.assertIs(result.report.tokenizer_exact, True)
        self.assertGreater(result.report.source_token_estimate, 0)
        self.assertGreater(result.report.output_token_estimate, 0)
        self.assertEqual(backend.last_count_model, "gemini-test")


if __name__ == "__main__":
    unittest.main()
