#!/usr/bin/env python3
"""Protocol-aware system instruction injection for grok2api requests."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import signal
import sys
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


CHAT_COMPLETIONS_PATH = "/v1/chat/completions"
RESPONSES_PATH = "/v1/responses"
ANTHROPIC_MESSAGES_PATH = "/v1/messages"
INJECTION_PATHS = frozenset(
    {CHAT_COMPLETIONS_PATH, RESPONSES_PATH, ANTHROPIC_MESSAGES_PATH}
)
HEALTH_PATH = "/_system-instruction/health"
DEFAULT_MAX_BODY_BYTES = 32 << 20
HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


class InjectionError(ValueError):
    """The request cannot be safely rewritten with the fixed instruction."""


class RequestError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class ProxyConfig:
    upstream_host: str
    upstream_port: int
    instruction: str
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    upstream_timeout: float = 900.0
    parse_concurrency: int = 1

    def __post_init__(self) -> None:
        if not self.instruction.strip():
            raise ValueError("fixed system instruction must not be empty")
        if not 1 <= self.upstream_port <= 65535:
            raise ValueError("upstream port must be between 1 and 65535")
        if self.max_body_bytes <= 0:
            raise ValueError("max body bytes must be positive")
        if self.upstream_timeout <= 0:
            raise ValueError("upstream timeout must be positive")
        if self.parse_concurrency <= 0:
            raise ValueError("parse concurrency must be positive")


def _reject_nonstandard_number(value: str) -> None:
    raise InjectionError(f"request body contains unsupported JSON number {value}")


def _parse_object(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body, parse_constant=_reject_nonstandard_number)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InjectionError("request body must be valid JSON") from error
    if not isinstance(payload, dict):
        raise InjectionError("request body must be a JSON object")
    return payload


def _prepend_text(fixed: str, client: str) -> str:
    return fixed if not client else f"{fixed}\n\n{client}"


def inject_instruction(path: str, body: bytes, instruction: str) -> bytes:
    """Return a request body with the fixed instruction inserted first."""
    if path not in INJECTION_PATHS:
        return body
    if not instruction.strip():
        raise InjectionError("fixed system instruction must not be empty")

    payload = _parse_object(body)

    if path == CHAT_COMPLETIONS_PATH:
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise InjectionError("Chat Completions request must contain a messages array")
        payload["messages"] = [
            {"role": "system", "content": instruction},
            *messages,
        ]
    elif path == RESPONSES_PATH:
        client_instruction = payload.get("instructions")
        if client_instruction is None:
            payload["instructions"] = instruction
        elif isinstance(client_instruction, str):
            payload["instructions"] = _prepend_text(instruction, client_instruction)
        else:
            raise InjectionError("Responses request instructions must be an instructions string")
    else:
        client_system = payload.get("system")
        if client_system is None:
            payload["system"] = instruction
        elif isinstance(client_system, str):
            payload["system"] = _prepend_text(instruction, client_system)
        elif isinstance(client_system, list):
            payload["system"] = [
                {"type": "text", "text": instruction},
                *client_system,
            ]
        else:
            raise InjectionError("Anthropic request system must be a system string or array")

    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class SystemInstructionProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], config: ProxyConfig) -> None:
        self.config = config
        self.parse_slots = threading.BoundedSemaphore(config.parse_concurrency)
        super().__init__(server_address, SystemInstructionProxyHandler)


class SystemInstructionProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "grok-system-instruction-proxy/1"
    sys_version = ""

    def do_DELETE(self) -> None:
        self._proxy_request()

    def do_GET(self) -> None:
        self._proxy_request()

    def do_HEAD(self) -> None:
        self._proxy_request()

    def do_OPTIONS(self) -> None:
        self._proxy_request()

    def do_PATCH(self) -> None:
        self._proxy_request()

    def do_POST(self) -> None:
        self._proxy_request()

    def do_PUT(self) -> None:
        self._proxy_request()

    @property
    def proxy_server(self) -> SystemInstructionProxyServer:
        return self.server  # type: ignore[return-value]

    def _proxy_request(self) -> None:
        request_path = urlsplit(self.path).path
        if self.command == "GET" and request_path == HEALTH_PATH:
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return

        should_inject = self.command == "POST" and request_path in INJECTION_PATHS
        slot = self.proxy_server.parse_slots if should_inject else None
        if slot is not None:
            slot.acquire()

        upstream: http.client.HTTPConnection | None = None
        try:
            if should_inject:
                self._validate_injection_headers()
            body, had_body = self._read_request_body()
            if should_inject:
                try:
                    body = inject_instruction(
                        request_path,
                        body,
                        self.proxy_server.config.instruction,
                    )
                except InjectionError as error:
                    raise RequestError(HTTPStatus.BAD_REQUEST, str(error)) from error
                had_body = True

            upstream = http.client.HTTPConnection(
                self.proxy_server.config.upstream_host,
                self.proxy_server.config.upstream_port,
                timeout=self.proxy_server.config.upstream_timeout,
            )
            upstream.request(
                self.command,
                self.path,
                body=body if had_body else None,
                headers=self._upstream_headers(len(body) if had_body else None),
            )
            del body
            if slot is not None:
                slot.release()
                slot = None

            response = upstream.getresponse()
            try:
                self._relay_response(response, should_inject, request_path)
            finally:
                response.close()
        except RequestError as error:
            self._write_protocol_error(error.status, str(error), request_path)
        except (OSError, http.client.HTTPException) as error:
            self.log_error("upstream request failed path=%s error=%s", request_path, type(error).__name__)
            self._write_protocol_error(
                HTTPStatus.BAD_GATEWAY,
                "system instruction proxy could not reach grok2api",
                request_path,
            )
        finally:
            if slot is not None:
                slot.release()
            if upstream is not None:
                upstream.close()

    def _validate_injection_headers(self) -> None:
        content_encoding = self.headers.get("Content-Encoding", "identity").strip().lower()
        if content_encoding not in {"", "identity"}:
            self.close_connection = True
            raise RequestError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "compressed conversation request bodies are not supported",
            )
        content_type = self.headers.get("Content-Type", "").partition(";")[0].strip().lower()
        if content_type != "application/json":
            self.close_connection = True
            raise RequestError(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                "conversation request body must use application/json",
            )

    def _read_request_body(self) -> tuple[bytes, bool]:
        transfer_encoding = self.headers.get("Transfer-Encoding", "").strip().lower()
        content_length = self.headers.get("Content-Length")
        if transfer_encoding and transfer_encoding != "chunked":
            self.close_connection = True
            raise RequestError(HTTPStatus.BAD_REQUEST, "unsupported request transfer encoding")
        if transfer_encoding == "chunked" and content_length is not None:
            self.close_connection = True
            raise RequestError(HTTPStatus.BAD_REQUEST, "ambiguous request body framing")
        if transfer_encoding == "chunked":
            return self._read_chunked_body(), True
        if content_length is None:
            return b"", False
        try:
            length = int(content_length, 10)
        except ValueError as error:
            self.close_connection = True
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid content length") from error
        if length < 0:
            self.close_connection = True
            raise RequestError(HTTPStatus.BAD_REQUEST, "invalid content length")
        if length > self.proxy_server.config.max_body_bytes:
            self.close_connection = True
            raise RequestError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body exceeds configured limit")
        body = self.rfile.read(length)
        if len(body) != length:
            self.close_connection = True
            raise RequestError(HTTPStatus.BAD_REQUEST, "incomplete request body")
        return body, True

    def _read_chunked_body(self) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            line = self.rfile.readline(8193)
            if not line or len(line) > 8192 or not line.endswith(b"\n"):
                self.close_connection = True
                raise RequestError(HTTPStatus.BAD_REQUEST, "invalid chunked request body")
            size_token = line.split(b";", 1)[0].strip()
            try:
                size = int(size_token, 16)
            except ValueError as error:
                self.close_connection = True
                raise RequestError(HTTPStatus.BAD_REQUEST, "invalid chunked request body") from error
            if size < 0:
                self.close_connection = True
                raise RequestError(HTTPStatus.BAD_REQUEST, "invalid chunked request body")
            if size == 0:
                self._consume_request_trailers()
                return b"".join(chunks)
            total += size
            if total > self.proxy_server.config.max_body_bytes:
                self.close_connection = True
                raise RequestError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "request body exceeds configured limit")
            chunk = self.rfile.read(size)
            delimiter = self.rfile.read(2)
            if len(chunk) != size or delimiter != b"\r\n":
                self.close_connection = True
                raise RequestError(HTTPStatus.BAD_REQUEST, "invalid chunked request body")
            chunks.append(chunk)

    def _consume_request_trailers(self) -> None:
        while True:
            line = self.rfile.readline(8193)
            if not line or len(line) > 8192:
                self.close_connection = True
                raise RequestError(HTTPStatus.BAD_REQUEST, "invalid chunked request trailer")
            if line in {b"\r\n", b"\n"}:
                return

    def _upstream_headers(self, content_length: int | None) -> dict[str, str]:
        headers: dict[str, str] = {}
        for name, value in self.headers.items():
            lowered = name.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered in {"content-length", "expect"}:
                continue
            headers[name] = value
        if content_length is not None:
            headers["Content-Length"] = str(content_length)
        return headers

    def _relay_response(
        self,
        response: http.client.HTTPResponse,
        instruction_applied: bool,
        request_path: str,
    ) -> None:
        self.send_response(response.status, response.reason)
        response_has_body = self.command != "HEAD" and not (
            100 <= response.status < 200 or response.status in {204, 304}
        )
        upstream_length = response.getheader("Content-Length")
        chunk_downstream = response_has_body and (response.chunked or upstream_length is None)

        for name, value in response.getheaders():
            lowered = name.lower()
            if lowered in HOP_BY_HOP_HEADERS or lowered == "x-system-instruction-applied":
                continue
            if lowered == "content-length" and chunk_downstream:
                continue
            self.send_header(name, value)
        if instruction_applied:
            self.send_header("X-System-Instruction-Applied", "1")
        if chunk_downstream:
            self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        if response_has_body:
            try:
                while True:
                    chunk = response.read1(16 << 10)
                    if not chunk:
                        break
                    if chunk_downstream:
                        self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                        self.wfile.write(chunk + b"\r\n")
                    else:
                        self.wfile.write(chunk)
                    self.wfile.flush()
                if chunk_downstream:
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True
                return

        if instruction_applied:
            self.log_message("injected fixed system instruction path=%s status=%d", request_path, response.status)

    def _write_protocol_error(self, status: int, message: str, path: str) -> None:
        if path == ANTHROPIC_MESSAGES_PATH:
            payload: dict[str, Any] = {
                "type": "error",
                "error": {"type": "invalid_request_error", "message": message},
            }
        else:
            payload = {
                "error": {
                    "message": message,
                    "type": "invalid_request_error",
                    "code": "system_instruction_injection_failed",
                }
            }
        self._write_json(status, payload)

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
            self.wfile.flush()

    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        del size
        self.log_message(
            "%s %s status=%s",
            self.command,
            urlsplit(self.path).path,
            code,
        )

    def log_message(self, format: str, *args: object) -> None:
        sys.stderr.write(
            "%s - - [%s] %s\n"
            % (self.address_string(), self.log_date_time_string(), format % args)
        )


def create_server(host: str, port: int, config: ProxyConfig) -> SystemInstructionProxyServer:
    return SystemInstructionProxyServer((host, port), config)


def load_instruction(path: str) -> str:
    try:
        instruction = Path(path).read_bytes().decode("utf-8-sig").rstrip("\r\n")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("system instruction file must be readable UTF-8") from error
    if not instruction.strip():
        raise ValueError("system instruction file must not be empty")
    return instruction


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-host", default=os.getenv("LISTEN_HOST", "127.0.0.1"))
    parser.add_argument("--listen-port", type=int, default=int(os.getenv("LISTEN_PORT", "8001")))
    parser.add_argument("--upstream-host", default=os.getenv("UPSTREAM_HOST", "127.0.0.1"))
    parser.add_argument("--upstream-port", type=int, default=int(os.getenv("UPSTREAM_PORT", "8000")))
    parser.add_argument("--instruction-file", default=os.getenv("SYSTEM_INSTRUCTION_FILE"), required=os.getenv("SYSTEM_INSTRUCTION_FILE") is None)
    parser.add_argument("--max-body-bytes", type=int, default=int(os.getenv("MAX_BODY_BYTES", str(DEFAULT_MAX_BODY_BYTES))))
    parser.add_argument("--upstream-timeout", type=float, default=float(os.getenv("UPSTREAM_TIMEOUT", "900")))
    parser.add_argument("--parse-concurrency", type=int, default=int(os.getenv("PARSE_CONCURRENCY", "1")))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config = ProxyConfig(
            upstream_host=args.upstream_host,
            upstream_port=args.upstream_port,
            instruction=load_instruction(args.instruction_file),
            max_body_bytes=args.max_body_bytes,
            upstream_timeout=args.upstream_timeout,
            parse_concurrency=args.parse_concurrency,
        )
        server = create_server(args.listen_host, args.listen_port, config)
    except (OSError, ValueError) as error:
        print(f"configuration error: {error}", file=sys.stderr)
        return 2

    def stop_server(_signum: int, _frame: Any) -> None:
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop_server)
    signal.signal(signal.SIGINT, stop_server)
    print(
        f"system instruction proxy listening on {args.listen_host}:{args.listen_port} "
        f"and forwarding to {config.upstream_host}:{config.upstream_port}",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
