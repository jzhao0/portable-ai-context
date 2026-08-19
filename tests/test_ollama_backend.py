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
    DEFAULT_OLLAMA_API_BASE,
    DEFAULT_OLLAMA_NUM_PREDICT,
    BackendConfig,
    OllamaBackend,
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


def _response_body(
    *,
    content="SAFE RESULT",
    done=True,
    done_reason="stop",
    thinking=None,
    tool_calls=None,
    include_done_reason=True,
):
    message = {"role": "assistant", "content": content}
    if thinking is not None:
        message["thinking"] = thinking
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    value = {
        "model": "test-model",
        "message": message,
        "done": done,
    }
    if include_done_reason:
        value["done_reason"] = done_reason
    return json.dumps(value).encode("utf-8")


class OllamaBackendTransportTests(unittest.TestCase):
    def setUp(self):
        self.system = "PRIVATE_SYSTEM_PROMPT_CONTENT"
        self.user = "PRIVATE_USER_PROMPT_CONTENT"
        self.backend = OllamaBackend(
            api_base="http://localhost:11434",
            num_predict=777,
            timeout=19,
        )

    def _complete(self, model="qwen3:8b"):
        return self.backend.complete(
            model=model,
            system=self.system,
            user=self.user,
            stage="map",
        )

    def _assert_content_safe(self, message: str, *extra_private_values: str):
        for value in (self.system, self.user, *extra_private_values):
            self.assertNotIn(value, message)

    def test_request_matches_native_chat_contract_without_default_auth(self):
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return _Response(_response_body())

        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            result = self._complete()

        self.assertEqual(result, "SAFE RESULT")
        request = captured["request"]
        self.assertEqual(request.full_url, "http://localhost:11434/api/chat")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(captured["timeout"], 19)
        headers = {key.lower(): value for key, value in request.header_items()}
        self.assertEqual(headers["content-type"], "application/json")
        self.assertNotIn("authorization", headers)

        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "qwen3:8b")
        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": self.system},
                {"role": "user", "content": self.user},
            ],
        )
        self.assertIs(payload["stream"], False)
        self.assertIs(payload["think"], False)
        self.assertEqual(
            payload["options"],
            {"num_predict": 777, "temperature": 0.1},
        )
        self.assertNotIn("stage", payload)
        self.assertNotIn("tools", payload)

    def test_explicit_api_key_adds_bearer_header_only_when_configured(self):
        backend = OllamaBackend(
            api_base="https://remote.example/ollama",
            api_key="PRIVATE_OLLAMA_KEY",
        )
        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            return _Response(_response_body())

        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            backend.complete(
                model="namespace/model:tag",
                system="system",
                user="user",
                stage="final",
            )

        headers = {key.lower(): value for key, value in captured["request"].header_items()}
        self.assertEqual(headers["authorization"], "Bearer PRIVATE_OLLAMA_KEY")
        self.assertEqual(
            captured["request"].full_url,
            "https://remote.example/ollama/api/chat",
        )

    def test_host_and_api_bases_normalize_to_one_api_chat_suffix(self):
        cases = {
            "http://localhost:11434": "http://localhost:11434/api/chat",
            "http://localhost:11434/": "http://localhost:11434/api/chat",
            "http://localhost:11434/api": "http://localhost:11434/api/chat",
            "http://localhost:11434/api/": "http://localhost:11434/api/chat",
            "https://remote.example/ollama": "https://remote.example/ollama/api/chat",
            "https://remote.example/ollama/api": "https://remote.example/ollama/api/chat",
        }
        for base, endpoint in cases.items():
            with self.subTest(base=base):
                backend = OllamaBackend(api_base=base)
                self.assertEqual(backend.chat_url, endpoint)

    def test_unsafe_api_bases_are_rejected_without_echo(self):
        unsafe = (
            "file:///PRIVATE_PATH",
            "http://PRIVATE_USER:PRIVATE_PASS@localhost:11434",
            "http://localhost:11434?PRIVATE_QUERY=1",
            "http://localhost:11434/#PRIVATE_FRAGMENT",
            "http://localhost:11434/../PRIVATE_PATH",
            "http://localhost:11434/%2e%2e/PRIVATE_PATH",
            r"http://localhost:11434/..\PRIVATE_PATH",
            " http://localhost:11434",
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

    def test_model_names_allow_tags_and_namespaces_but_reject_unsafe_values(self):
        for model in ("qwen3:8b", "namespace/model:tag", "model@sha256:abc123"):
            with self.subTest(model=model):
                with mock.patch(
                    "portable_ai_context.compiler.ollama.urllib.request.urlopen",
                    return_value=_Response(_response_body()),
                ):
                    self.assertEqual(self._complete(model), "SAFE RESULT")

        unsafe = (
            "",
            " model",
            "model ",
            "model with spaces",
            "model\nPRIVATE_MODEL",
            "x" * 257,
        )
        for model in unsafe:
            with self.subTest(model=model):
                with self.assertRaises(CompilerError) as caught:
                    self._complete(model)
                self.assertEqual(
                    str(caught.exception),
                    "ollama backend model identifier is invalid",
                )
                self.assertNotIn("PRIVATE_MODEL", str(caught.exception))

    def test_thinking_is_ignored_even_when_server_returns_it(self):
        private_thinking = "PRIVATE_REASONING_TRACE"
        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            return_value=_Response(_response_body(content="final", thinking=private_thinking)),
        ):
            result = self._complete()
        self.assertEqual(result, "final")
        self.assertNotIn(private_thinking, result)

    def test_malformed_thinking_type_fails_without_echo(self):
        body = json.dumps(
            {
                "message": {
                    "role": "assistant",
                    "content": "PRIVATE_CONTENT",
                    "thinking": {"private": "PRIVATE_REASONING"},
                },
                "done": True,
                "done_reason": "stop",
            }
        ).encode("utf-8")
        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            return_value=_Response(body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "unexpected Ollama response shape")
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_done_stop_and_legacy_missing_reason_are_success(self):
        responses = (
            _response_body(done_reason="stop"),
            _response_body(done_reason="", include_done_reason=True),
            _response_body(include_done_reason=False),
        )
        for body in responses:
            with self.subTest(body=body):
                with mock.patch(
                    "portable_ai_context.compiler.ollama.urllib.request.urlopen",
                    return_value=_Response(body),
                ):
                    self.assertEqual(self._complete(), "SAFE RESULT")

    def test_length_done_reason_is_explicit_truncation_failure(self):
        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            return_value=_Response(
                _response_body(content="PRIVATE_PARTIAL_TEXT", done_reason="length")
            ),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "ollama backend output reached num_predict")
        self.assertNotIn("PRIVATE_PARTIAL_TEXT", str(caught.exception))

    def test_nonempty_unknown_done_reasons_fail_closed_without_echo(self):
        for reason in ("load", "unload", "PRIVATE_FUTURE_REASON"):
            with self.subTest(reason=reason):
                with mock.patch(
                    "portable_ai_context.compiler.ollama.urllib.request.urlopen",
                    return_value=_Response(_response_body(done_reason=reason)),
                ):
                    with self.assertRaises(CompilerError) as caught:
                        self._complete()
                self.assertEqual(
                    str(caught.exception),
                    "ollama backend returned an unsupported done reason",
                )
                self.assertNotIn(reason, str(caught.exception))

    def test_done_false_is_incomplete_even_if_content_exists(self):
        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            return_value=_Response(_response_body(content="PRIVATE_PARTIAL", done=False)),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(
            str(caught.exception),
            "ollama backend returned an incomplete response",
        )
        self.assertNotIn("PRIVATE_PARTIAL", str(caught.exception))

    def test_nonempty_tool_calls_fail_closed_without_echoing_payload(self):
        tool_calls = [
            {
                "function": {
                    "name": "PRIVATE_TOOL_NAME",
                    "arguments": {"secret": "PRIVATE_TOOL_ARGUMENT"},
                }
            }
        ]
        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            return_value=_Response(_response_body(content="", tool_calls=tool_calls)),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(
            str(caught.exception),
            "ollama backend returned an unexpected tool-use result",
        )
        self.assertNotIn("PRIVATE", str(caught.exception))

    def test_empty_tool_calls_are_allowed(self):
        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            return_value=_Response(_response_body(content="final", tool_calls=[])),
        ):
            self.assertEqual(self._complete(), "final")

    def test_malformed_shapes_fail_cleanly(self):
        bodies = (
            json.dumps([]).encode("utf-8"),
            json.dumps({"done": True, "done_reason": 123, "message": {}}).encode("utf-8"),
            json.dumps({"done": True, "done_reason": "stop", "message": "PRIVATE"}).encode("utf-8"),
            json.dumps({"done": True, "done_reason": "stop", "message": {"role": "user", "content": "PRIVATE"}}).encode("utf-8"),
            json.dumps({"done": True, "done_reason": "stop", "message": {"role": "assistant", "content": 123}}).encode("utf-8"),
            json.dumps({"done": True, "done_reason": "stop", "message": {"role": "assistant", "content": "safe", "tool_calls": "PRIVATE"}}).encode("utf-8"),
        )
        for body in bodies:
            with self.subTest(body=body[:40]):
                with mock.patch(
                    "portable_ai_context.compiler.ollama.urllib.request.urlopen",
                    return_value=_Response(body),
                ):
                    with self.assertRaises(CompilerError) as caught:
                        self._complete()
                self.assertEqual(str(caught.exception), "unexpected Ollama response shape")
                self.assertNotIn("PRIVATE", str(caught.exception))

    def test_empty_final_content_fails(self):
        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            return_value=_Response(_response_body(content="   ")),
        ):
            with self.assertRaisesRegex(CompilerError, "returned no text content"):
                self._complete()

    def test_invalid_json_does_not_echo_response_body(self):
        private_body = b"PRIVATE_INVALID_OLLAMA_JSON {"
        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            return_value=_Response(private_body),
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "ollama backend returned invalid JSON")
        self._assert_content_safe(str(caught.exception), private_body.decode("utf-8"))

    def test_http_error_reports_only_status(self):
        private_body = "PRIVATE_OLLAMA_ERROR_BODY"
        error = urllib.error.HTTPError(
            url="http://localhost:11434/api/chat",
            code=500,
            msg="PRIVATE_HTTP_REASON",
            hdrs=None,
            fp=io.BytesIO(private_body.encode("utf-8")),
        )
        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "ollama backend HTTP status 500")
        self._assert_content_safe(str(caught.exception), private_body, "PRIVATE_HTTP_REASON")
        self.assertIs(caught.exception.__cause__, error)

    def test_transport_error_is_generic(self):
        private_reason = "PRIVATE_OLLAMA_TRANSPORT_DETAIL"
        error = urllib.error.URLError(private_reason)
        with mock.patch(
            "portable_ai_context.compiler.ollama.urllib.request.urlopen",
            side_effect=error,
        ):
            with self.assertRaises(CompilerError) as caught:
                self._complete()
        self.assertEqual(str(caught.exception), "ollama backend transport failed")
        self._assert_content_safe(str(caught.exception), private_reason)
        self.assertIs(caught.exception.__cause__, error)


class OllamaBackendRegistryTests(unittest.TestCase):
    def test_ollama_is_registered_keyless_by_default(self):
        self.assertIn("ollama", available_backends())
        backend = create_backend(
            "ollama",
            BackendConfig(
                environment={"PAIC_API_KEY": "PRIVATE_GLOBAL_KEY_MUST_BE_IGNORED"},
            ),
        )
        self.assertIsInstance(backend, OllamaBackend)
        self.assertEqual(backend.api_base, DEFAULT_OLLAMA_API_BASE)
        self.assertEqual(backend.num_predict, DEFAULT_OLLAMA_NUM_PREDICT)
        self.assertIsNone(backend.api_key)

    def test_factory_ignores_global_api_key_env_even_when_it_names_existing_secret(self):
        backend = create_backend(
            "ollama",
            BackendConfig(
                api_key_env="GLOBAL_PRIVATE_KEY",
                environment={"GLOBAL_PRIVATE_KEY": "PRIVATE_GLOBAL_VALUE"},
            ),
        )
        self.assertIsNone(backend.api_key)

    def test_factory_resolves_only_explicit_ollama_key_env(self):
        backend = create_backend(
            "ollama",
            BackendConfig(
                api_base="https://remote.example/ollama/api",
                api_key_env="GLOBAL_PRIVATE_KEY",
                environment={
                    "GLOBAL_PRIVATE_KEY": "PRIVATE_GLOBAL_VALUE",
                    "OLLAMA_API_KEY": "PRIVATE_OLLAMA_VALUE",
                },
                options={
                    "ollama_api_key_env": "OLLAMA_API_KEY",
                    "ollama_num_predict": 1234,
                },
                timeout=23,
            ),
        )
        self.assertEqual(backend.api_key, "PRIVATE_OLLAMA_VALUE")
        self.assertEqual(backend.num_predict, 1234)
        self.assertEqual(backend.timeout, 23)
        self.assertEqual(backend.chat_url, "https://remote.example/ollama/api/chat")

    def test_factory_rejects_invalid_num_predict(self):
        for value in (0, -1, True, "4096"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(CompilerError, "num_predict must be a positive integer"):
                    create_backend(
                        "ollama",
                        BackendConfig(options={"ollama_num_predict": value}),
                    )

    def test_explicit_key_env_must_be_valid_and_present(self):
        with self.assertRaisesRegex(CompilerError, "environment variable name is invalid"):
            create_backend(
                "ollama",
                BackendConfig(options={"ollama_api_key_env": "PRIVATE KEY NAME"}),
            )
        with self.assertRaisesRegex(CompilerError, "OLLAMA_API_KEY"):
            create_backend(
                "ollama",
                BackendConfig(
                    environment={},
                    options={"ollama_api_key_env": "OLLAMA_API_KEY"},
                ),
            )


class _RecordingBackend:
    def complete(self, *, model, system, user, stage):
        return "safe compiled output"


class OllamaBackendCliTests(unittest.TestCase):
    def test_cli_forwards_ollama_options_without_requiring_global_api_key(self):
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
            backend = _RecordingBackend()
            with mock.patch(
                "portable_ai_context.cli.create_backend",
                return_value=backend,
            ) as create:
                with contextlib.redirect_stdout(io.StringIO()):
                    code = cli_main(
                        [
                            "compile",
                            str(source),
                            "-o",
                            str(root / "out"),
                            "--backend",
                            "ollama",
                            "--ollama-num-predict",
                            "7777",
                            "--ollama-api-key-env",
                            "OLLAMA_API_KEY",
                            "--map-model",
                            "qwen3:8b",
                            "--final-model",
                            "qwen3:8b",
                        ]
                    )

        self.assertEqual(code, 0)
        backend_name, config = create.call_args.args
        self.assertEqual(backend_name, "ollama")
        self.assertEqual(config.options["ollama_num_predict"], 7777)
        self.assertEqual(config.options["ollama_api_key_env"], "OLLAMA_API_KEY")
        self.assertIs(config.environment, os.environ)


if __name__ == "__main__":
    unittest.main()
