from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from local_inference_test_bench.client import (  # noqa: E402
    ClientError,
    OpenAICompatibleClient,
)
import local_inference_test_bench.client as client_module  # noqa: E402
from local_inference_test_bench.models import GenerationSettings  # noqa: E402
from local_inference_test_bench.safety import (  # noqa: E402
    SafetyError,
    load_credential,
    validate_endpoint,
)


LOOPBACK = ".".join(("127", "0", "0", "1"))


def ipv4(first: int, second: int, third: int, fourth: int) -> str:
    value = (first << 24) | (second << 16) | (third << 8) | fourth
    return str(ipaddress.IPv4Address(value))


class DeterministicStubHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A002, ANN001
        return

    def _send(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        self.close_connection = True

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/v1/models":
            self._send(404, {"error": {"code": "missing"}})
            return
        self.server.seen_authorization = self.headers.get("Authorization")
        payload = (
            {"object": "list"}
            if self.server.omit_model_metadata
            else {"object": "list", "data": [{"id": "stub-model"}]}
        )
        self._send(200, payload)

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        request = json.loads(self.rfile.read(length).decode("utf-8"))
        self.server.last_request = request
        if request.get("model") == "context-error":
            self._send(
                400,
                {
                    "error": {
                        "code": "context_length_exceeded",
                        "message": "request exceeds the context window",
                    }
                },
            )
            return
        if request.get("model") == "reasoning-only":
            self._send(
                200,
                {
                    "model": "reasoning-only",
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "reasoning_content": "transient internal analysis",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": 9,
                        "total_tokens": 14,
                    },
                },
            )
            return
        if request.get("model") == "metadata-absent":
            self._send(
                200,
                {
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "synthetic-output"},
                            "finish_reason": None,
                        }
                    ]
                },
            )
            return
        if request.get("model") == "partial-usage":
            self._send(
                200,
                {
                    "model": "partial-usage",
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "synthetic-output"},
                            "finish_reason": "length",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 5,
                        "completion_tokens": -1,
                        "total_tokens": True,
                    },
                },
            )
            return
        if request.get("model") == "oversized-response":
            self._send(
                200,
                {
                    "model": "oversized-response",
                    "choices": [
                        {
                            "message": {"role": "assistant", "content": "x" * 256},
                            "finish_reason": "stop",
                        }
                    ],
                },
            )
            return
        self._send(
            200,
            {
                "model": "stub-model",
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "synthetic-output"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
            },
        )


class StubServer:
    def __enter__(self):
        self.server = ThreadingHTTPServer((LOOPBACK, 0), DeterministicStubHandler)
        self.server.daemon_threads = True
        self.server.seen_authorization = None
        self.server.last_request = None
        self.server.omit_model_metadata = False
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address
        self.endpoint = f"http://{host}:{port}"
        return self

    def __exit__(self, exc_type, exc, traceback):  # noqa: ANN001
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def answer(address: str) -> tuple:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, 80, 0, 0) if family == socket.AF_INET6 else (address, 80)
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


class EndpointSafetyTests(unittest.TestCase):
    def test_url_parsing_rejects_malformed_public_and_unresolved_endpoints(self) -> None:
        local_answer = lambda *args, **kwargs: [answer(LOOPBACK)]
        malformed = (
            "not-a-url",
            "ftp://inference.invalid",
            "http:///missing-host",
            "http://inference.invalid:70000",
        )
        for endpoint in malformed:
            with self.subTest(endpoint=endpoint), self.assertRaises(SafetyError):
                validate_endpoint(endpoint, resolver=local_answer)

        public = ipv4(8, 8, 4, 4)
        with self.assertRaisesRegex(SafetyError, "private or loopback"):
            validate_endpoint(
                "http://inference.invalid",
                resolver=lambda *args, **kwargs: [answer(public)],
            )
        with self.assertRaisesRegex(SafetyError, "could not be resolved"):
            validate_endpoint(
                "http://inference.invalid",
                resolver=lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror()),
            )

    def test_all_resolved_addresses_must_be_local(self) -> None:
        addresses = (ipv4(10, 2, 3, 4), ipv4(192, 168, 3, 4))
        result = validate_endpoint(
            "http://inference.invalid",
            resolver=lambda *args, **kwargs: [answer(address) for address in addresses],
        )
        self.assertEqual(result.addresses, tuple(sorted(addresses)))

    def test_rejects_documentation_address_even_if_ipaddress_marks_it_non_global(self) -> None:
        documentation_address = ipv4(192, 0, 2, 1)
        with self.assertRaisesRegex(SafetyError, "private or loopback"):
            validate_endpoint(
                f"http://{documentation_address}",
                resolver=lambda *args, **kwargs: [answer(documentation_address)],
            )

    def test_rejects_mixed_private_and_public_dns_answers(self) -> None:
        private = ipv4(10, 1, 2, 3)
        public = ipv4(8, 8, 8, 8)
        with self.assertRaisesRegex(SafetyError, "only"):
            validate_endpoint(
                "http://inference.invalid",
                resolver=lambda *args, **kwargs: [answer(private), answer(public)],
            )

    def test_accepts_explicit_private_and_loopback_ranges(self) -> None:
        for address in (
            ipv4(127, 0, 0, 2),
            ipv4(10, 2, 3, 4),
            ipv4(172, 20, 4, 5),
            ipv4(192, 168, 4, 5),
            str(ipaddress.IPv6Address((0xFD << 120) | 5)),
            str(ipaddress.IPv6Address(1)),
        ):
            rendered = f"[{address}]" if ":" in address else address
            result = validate_endpoint(
                f"http://{rendered}",
                resolver=lambda *args, _address=address, **kwargs: [answer(_address)],
            )
            self.assertEqual(result.addresses, (address,))

    def test_rejects_credentials_query_fragment_and_unapproved_path(self) -> None:
        resolver = lambda *args, **kwargs: [answer(LOOPBACK)]
        unsafe = (
            f"http://name:value@{LOOPBACK}",
            f"http://{LOOPBACK}?key=value",
            f"http://{LOOPBACK}#fragment",
            f"http://{LOOPBACK}/admin",
        )
        for endpoint in unsafe:
            with self.subTest(endpoint=endpoint), self.assertRaises(SafetyError):
                validate_endpoint(endpoint, resolver=resolver)

    def test_credentials_come_only_from_approved_environment_sources(self) -> None:
        self.assertIsNone(load_credential(None, environ={}))
        self.assertEqual(
            load_credential("INFERENCE_TEST_TOKEN", environ={"INFERENCE_TEST_TOKEN": "placeholder"}),
            "placeholder",
        )
        with self.assertRaisesRegex(SafetyError, "approved environment source"):
            load_credential("INFERENCE_TEST_TOKEN", environ={})

    def test_environment_file_must_be_owner_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / ".env"
            path.write_text("INFERENCE_TEST_TOKEN=placeholder\n", encoding="utf-8")
            if sys.platform != "win32":
                path.chmod(0o600)
            self.assertEqual(
                load_credential("INFERENCE_TEST_TOKEN", env_file=path, environ={}),
                "placeholder",
            )
            if sys.platform != "win32":
                path.chmod(0o644)
                with self.assertRaisesRegex(SafetyError, "owner-only"):
                    load_credential("INFERENCE_TEST_TOKEN", env_file=path, environ={})


class ClientIntegrationTests(unittest.TestCase):
    def test_request_envelope_includes_only_supported_generation_and_tool_fields(self) -> None:
        tool = {
            "type": "function",
            "function": {
                "name": "lookup_synthetic_record",
                "description": "inert read-only lookup",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        with StubServer() as stub:
            client = OpenAICompatibleClient(stub.endpoint, timeout_seconds=2)
            client.chat_completions(
                model="stub-model",
                messages=({"role": "user", "content": "synthetic request"},),
                settings=GenerationSettings(
                    temperature=0.25,
                    top_p=0.75,
                    max_output_tokens=32,
                    seed=11,
                ),
                tools=(tool,),
            )

        self.assertEqual(
            set(stub.server.last_request),
            {"model", "messages", "temperature", "top_p", "max_tokens", "seed", "tools", "tool_choice"},
        )
        self.assertEqual(stub.server.last_request["tool_choice"], "auto")
        self.assertEqual(stub.server.last_request["tools"], [tool])
        self.assertNotIn("stream", stub.server.last_request)

    def test_runtime_and_usage_metadata_absence_are_normalized(self) -> None:
        with StubServer() as stub:
            stub.server.omit_model_metadata = True
            client = OpenAICompatibleClient(stub.endpoint, timeout_seconds=2)
            self.assertEqual(client.list_models(), ())
            absent = client.chat_completions(
                model="metadata-absent",
                messages=({"role": "user", "content": "synthetic request"},),
                settings=GenerationSettings(max_output_tokens=32),
            )
            partial = client.chat_completions(
                model="partial-usage",
                messages=({"role": "user", "content": "synthetic request"},),
                settings=GenerationSettings(max_output_tokens=32),
            )

        self.assertIsNone(absent.runtime_model)
        self.assertIsNone(absent.finish_reason)
        self.assertEqual(
            (absent.usage.prompt_tokens, absent.usage.completion_tokens, absent.usage.total_tokens),
            (None, None, None),
        )
        self.assertEqual(
            (partial.usage.prompt_tokens, partial.usage.completion_tokens, partial.usage.total_tokens),
            (5, None, None),
        )
        self.assertEqual(partial.finish_reason, "length")

    def test_response_size_limit_fails_with_a_categorical_error(self) -> None:
        with StubServer() as stub, patch.object(client_module, "MAX_RESPONSE_BYTES", 64):
            client = OpenAICompatibleClient(stub.endpoint, timeout_seconds=2)
            with self.assertRaises(ClientError) as captured:
                client.chat_completions(
                    model="oversized-response",
                    messages=({"role": "user", "content": "synthetic request"},),
                    settings=GenerationSettings(max_output_tokens=32),
                )

        self.assertEqual(captured.exception.category, "response_too_large")
        self.assertEqual(str(captured.exception), "inference request failed")

    def test_models_and_chat_completions_against_deterministic_stub(self) -> None:
        with StubServer() as stub:
            client = OpenAICompatibleClient(
                stub.endpoint,
                api_key="placeholder-only",
                timeout_seconds=2,
            )
            models = client.list_models()
            result = client.chat_completions(
                model="stub-model",
                messages=({"role": "user", "content": "synthetic request"},),
                settings=GenerationSettings(max_output_tokens=32),
            )

        self.assertEqual(models, ("stub-model",))
        self.assertEqual(result.content, "synthetic-output")
        self.assertEqual(result.usage.total_tokens, 7)
        self.assertEqual(stub.server.seen_authorization, "Bearer placeholder-only")
        self.assertEqual(stub.server.last_request["max_tokens"], 32)

    def test_context_error_is_categorical_and_sanitized(self) -> None:
        with StubServer() as stub:
            client = OpenAICompatibleClient(stub.endpoint, timeout_seconds=2)
            with self.assertRaises(ClientError) as captured:
                client.chat_completions(
                    model="context-error",
                    messages=({"role": "user", "content": "synthetic request"},),
                    settings=GenerationSettings(max_output_tokens=32),
                )

        self.assertEqual(captured.exception.category, "context_window")
        self.assertEqual(str(captured.exception), "inference request failed")
        self.assertNotIn(stub.endpoint, str(captured.exception))

    def test_reasoning_text_is_reduced_to_presence_boolean(self) -> None:
        with StubServer() as stub:
            client = OpenAICompatibleClient(stub.endpoint, timeout_seconds=2)
            result = client.chat_completions(
                model="reasoning-only",
                messages=({"role": "user", "content": "synthetic request"},),
                settings=GenerationSettings(max_output_tokens=32),
            )

        self.assertEqual(result.content, "")
        self.assertTrue(result.reasoning_present)
        self.assertFalse(hasattr(result, "reasoning_content"))
        self.assertNotIn("internal analysis", repr(result))


if __name__ == "__main__":
    unittest.main()
