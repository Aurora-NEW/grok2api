import json
import http.client
import io
import queue
import threading
import unittest
from contextlib import contextmanager, redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Iterator

from scripts.system_instruction_proxy import (
    InjectionError,
    ProxyConfig,
    create_server,
    inject_instruction,
)


FIXED_INSTRUCTION = "Gateway rule one.\nGateway rule two."


def decode(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


class CaptureUpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        self.server.requests.put((self.command, self.path, self.headers, b""))
        self._write_json_response()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        self.server.requests.put((self.command, self.path, self.headers, body))
        if self.headers.get("X-Test-Response") == "sse":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for chunk in (b'data: {"delta":"one"}\n\n', b"data: [DONE]\n\n"):
                self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                self.wfile.write(chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
            return
        self._write_json_response()

    def _write_json_response(self) -> None:
        body = b'{"upstream":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def running_server(server: ThreadingHTTPServer) -> Iterator[ThreadingHTTPServer]:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@contextmanager
def proxy_pair(*, max_body_bytes: int = 32 << 20) -> Iterator[tuple[ThreadingHTTPServer, ThreadingHTTPServer]]:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), CaptureUpstreamHandler)
    upstream.requests = queue.Queue()
    config = ProxyConfig(
        upstream_host="127.0.0.1",
        upstream_port=upstream.server_address[1],
        instruction=FIXED_INSTRUCTION,
        max_body_bytes=max_body_bytes,
        upstream_timeout=2,
    )
    proxy = create_server("127.0.0.1", 0, config)
    with running_server(upstream), running_server(proxy):
        yield upstream, proxy


class InjectInstructionTests(unittest.TestCase):
    def test_chat_completions_prepends_system_message(self) -> None:
        body = json.dumps(
            {
                "model": "grok-chat-fast",
                "messages": [
                    {"role": "system", "content": "Client rule."},
                    {"role": "user", "content": "Hello"},
                ],
                "stream": True,
            }
        ).encode()

        payload = decode(inject_instruction("/v1/chat/completions", body, FIXED_INSTRUCTION))

        self.assertEqual(
            payload["messages"],
            [
                {"role": "system", "content": FIXED_INSTRUCTION},
                {"role": "system", "content": "Client rule."},
                {"role": "user", "content": "Hello"},
            ],
        )
        self.assertTrue(payload["stream"])

    def test_responses_sets_missing_instructions(self) -> None:
        body = b'{"model":"grok-4.3","input":"Hello","stream":false}'

        payload = decode(inject_instruction("/v1/responses", body, FIXED_INSTRUCTION))

        self.assertEqual(payload["instructions"], FIXED_INSTRUCTION)
        self.assertEqual(payload["input"], "Hello")

    def test_responses_prepends_existing_instructions(self) -> None:
        body = b'{"model":"grok-4.3","instructions":"Client rule.","input":"Hello"}'

        payload = decode(inject_instruction("/v1/responses", body, FIXED_INSTRUCTION))

        self.assertEqual(payload["instructions"], f"{FIXED_INSTRUCTION}\n\nClient rule.")

    def test_anthropic_prepends_string_system(self) -> None:
        body = b'{"model":"grok-4.5","max_tokens":64,"system":"Client rule.","messages":[]}'

        payload = decode(inject_instruction("/v1/messages", body, FIXED_INSTRUCTION))

        self.assertEqual(payload["system"], f"{FIXED_INSTRUCTION}\n\nClient rule.")

    def test_anthropic_prepends_system_text_block(self) -> None:
        body = json.dumps(
            {
                "model": "grok-4.5",
                "max_tokens": 64,
                "system": [
                    {"type": "text", "text": "Client rule.", "cache_control": {"type": "ephemeral"}}
                ],
                "messages": [],
            }
        ).encode()

        payload = decode(inject_instruction("/v1/messages", body, FIXED_INSTRUCTION))

        self.assertEqual(payload["system"][0], {"type": "text", "text": FIXED_INSTRUCTION})
        self.assertEqual(payload["system"][1]["text"], "Client rule.")
        self.assertEqual(payload["system"][1]["cache_control"], {"type": "ephemeral"})

    def test_anthropic_sets_missing_system(self) -> None:
        body = b'{"model":"grok-4.5","max_tokens":64,"messages":[]}'

        payload = decode(inject_instruction("/v1/messages", body, FIXED_INSTRUCTION))

        self.assertEqual(payload["system"], FIXED_INSTRUCTION)

    def test_non_conversation_path_is_byte_for_byte_unchanged(self) -> None:
        body = b'{ "keep" : "spacing" }'

        self.assertEqual(inject_instruction("/v1/models", body, FIXED_INSTRUCTION), body)

    def test_rejects_invalid_json(self) -> None:
        with self.assertRaisesRegex(InjectionError, "valid JSON"):
            inject_instruction("/v1/responses", b"{invalid", FIXED_INSTRUCTION)

    def test_rejects_non_object_payload(self) -> None:
        with self.assertRaisesRegex(InjectionError, "JSON object"):
            inject_instruction("/v1/responses", b"[]", FIXED_INSTRUCTION)

    def test_rejects_chat_without_messages_array(self) -> None:
        with self.assertRaisesRegex(InjectionError, "messages array"):
            inject_instruction("/v1/chat/completions", b'{"messages":"bad"}', FIXED_INSTRUCTION)

    def test_rejects_non_string_responses_instructions(self) -> None:
        with self.assertRaisesRegex(InjectionError, "instructions string"):
            inject_instruction("/v1/responses", b'{"instructions":["bad"]}', FIXED_INSTRUCTION)

    def test_rejects_invalid_anthropic_system_shape(self) -> None:
        with self.assertRaisesRegex(InjectionError, "system string or array"):
            inject_instruction("/v1/messages", b'{"system":{"text":"bad"}}', FIXED_INSTRUCTION)

    def test_rejects_empty_fixed_instruction(self) -> None:
        with self.assertRaisesRegex(InjectionError, "must not be empty"):
            inject_instruction("/v1/responses", b'{"input":"Hello"}', "  \n")


class ProxyIntegrationTests(unittest.TestCase):
    def test_forwards_rewritten_body_authorization_and_content_length_response(self) -> None:
        with proxy_pair() as (upstream, proxy):
            connection = http.client.HTTPConnection(*proxy.server_address, timeout=2)
            connection.request(
                "POST",
                "/v1/responses?trace=test",
                body=b'{"model":"grok-4.3","input":"Hello"}',
                headers={
                    "Authorization": "Bearer integration-test",
                    "Content-Type": "application/json",
                },
            )
            response = connection.getresponse()
            response_body = response.read()
            connection.close()

            method, path, headers, captured_body = upstream.requests.get(timeout=1)
            self.assertEqual((method, path), ("POST", "/v1/responses?trace=test"))
            self.assertEqual(headers["Authorization"], "Bearer integration-test")
            self.assertEqual(decode(captured_body)["instructions"], FIXED_INSTRUCTION)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("X-System-Instruction-Applied"), "1")
            self.assertEqual(response_body, b'{"upstream":true}')

    def test_relays_chunked_sse_response(self) -> None:
        with proxy_pair() as (upstream, proxy):
            connection = http.client.HTTPConnection(*proxy.server_address, timeout=2)
            connection.request(
                "POST",
                "/v1/chat/completions",
                body=b'{"model":"grok-chat-fast","messages":[],"stream":true}',
                headers={
                    "Content-Type": "application/json",
                    "X-Test-Response": "sse",
                },
            )
            response = connection.getresponse()
            response_body = response.read()
            connection.close()

            upstream.requests.get(timeout=1)
            self.assertEqual(response.status, 200)
            self.assertEqual(response.getheader("Content-Type"), "text/event-stream")
            self.assertEqual(response.getheader("Transfer-Encoding"), "chunked")
            self.assertEqual(response_body, b'data: {"delta":"one"}\n\ndata: [DONE]\n\n')

    def test_accepts_chunked_json_request(self) -> None:
        with proxy_pair() as (upstream, proxy):
            connection = http.client.HTTPConnection(*proxy.server_address, timeout=2)
            chunks = iter([b'{"model":"grok-4.3",', b'"input":"Hello"}'])
            connection.request(
                "POST",
                "/v1/responses",
                body=chunks,
                headers={"Content-Type": "application/json"},
                encode_chunked=True,
            )
            response = connection.getresponse()
            response.read()
            connection.close()

            _, _, _, captured_body = upstream.requests.get(timeout=1)
            self.assertEqual(decode(captured_body)["instructions"], FIXED_INSTRUCTION)

    def test_rejects_compressed_conversation_request_without_upstream_call(self) -> None:
        with proxy_pair() as (upstream, proxy):
            connection = http.client.HTTPConnection(*proxy.server_address, timeout=2)
            connection.request(
                "POST",
                "/v1/responses",
                body=b"compressed",
                headers={
                    "Content-Type": "application/json",
                    "Content-Encoding": "gzip",
                },
            )
            response = connection.getresponse()
            response.read()
            connection.close()

            self.assertEqual(response.status, 415)
            with self.assertRaises(queue.Empty):
                upstream.requests.get(timeout=0.1)

    def test_rejects_oversized_conversation_request_without_upstream_call(self) -> None:
        with proxy_pair(max_body_bytes=16) as (upstream, proxy):
            connection = http.client.HTTPConnection(*proxy.server_address, timeout=2)
            connection.request(
                "POST",
                "/v1/responses",
                body=b'{"input":"this is too large"}',
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
            connection.close()

            self.assertEqual(response.status, 413)
            with self.assertRaises(queue.Empty):
                upstream.requests.get(timeout=0.1)

    def test_rejects_invalid_json_without_upstream_call(self) -> None:
        with proxy_pair() as (upstream, proxy):
            connection = http.client.HTTPConnection(*proxy.server_address, timeout=2)
            connection.request(
                "POST",
                "/v1/messages",
                body=b"{invalid",
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            response.read()
            connection.close()

            self.assertEqual(response.status, 400)
            self.assertEqual(response.getheader("X-System-Instruction-Applied"), None)
            with self.assertRaises(queue.Empty):
                upstream.requests.get(timeout=0.1)

    def test_health_endpoint_does_not_reach_upstream(self) -> None:
        with proxy_pair() as (upstream, proxy):
            connection = http.client.HTTPConnection(*proxy.server_address, timeout=2)
            connection.request("GET", "/_system-instruction/health")
            response = connection.getresponse()
            body = response.read()
            connection.close()

            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(body), {"status": "ok"})
            with self.assertRaises(queue.Empty):
                upstream.requests.get(timeout=0.1)

    def test_non_conversation_get_is_transparently_forwarded(self) -> None:
        with proxy_pair() as (upstream, proxy):
            connection = http.client.HTTPConnection(*proxy.server_address, timeout=2)
            connection.request("GET", "/v1/models")
            response = connection.getresponse()
            body = response.read()
            connection.close()

            method, path, _, captured_body = upstream.requests.get(timeout=1)
            self.assertEqual((method, path, captured_body), ("GET", "/v1/models", b""))
            self.assertEqual(response.status, 200)
            self.assertEqual(body, b'{"upstream":true}')

    def test_access_log_does_not_include_query_string(self) -> None:
        log_output = io.StringIO()
        with redirect_stderr(log_output), proxy_pair() as (upstream, proxy):
            connection = http.client.HTTPConnection(*proxy.server_address, timeout=2)
            connection.request("GET", "/v1/models?api_key=must-not-appear")
            response = connection.getresponse()
            response.read()
            connection.close()
            upstream.requests.get(timeout=1)

        self.assertNotIn("must-not-appear", log_output.getvalue())
        self.assertIn("GET /v1/models status=200", log_output.getvalue())


if __name__ == "__main__":
    unittest.main()
