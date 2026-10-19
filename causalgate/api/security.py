"""Transport controls for the single-tenant beta API (no model/provider calls)."""
from __future__ import annotations

import asyncio
import hmac
import json
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock


@dataclass(frozen=True)
class APISettings:
    api_key: str = field(default="", repr=False)
    policy_path: str | None = None
    audit_log_path: str | None = None
    enable_tool_guard: bool = False
    enable_docs: bool = False
    requests_per_minute: int = 60
    max_body_bytes: int = 65536
    body_timeout_seconds: float = 10.0

    def __post_init__(self):
        if self.api_key and (len(self.api_key) < 32 or not self.api_key.isascii() or any(c.isspace() for c in self.api_key)):
            raise ValueError("CAUSALGATE_API_KEY must contain at least 32 non-whitespace ASCII characters")
        if not 1 <= self.requests_per_minute <= 10000:
            raise ValueError("requests_per_minute must be between 1 and 10000")
        if not 1024 <= self.max_body_bytes <= 1048576:
            raise ValueError("max_body_bytes must be between 1024 and 1048576")
        if not math.isfinite(self.body_timeout_seconds) or not 0 < self.body_timeout_seconds <= 60:
            raise ValueError("body_timeout_seconds must be in (0, 60]")

    @classmethod
    def from_env(cls):
        def flag(name):
            value = os.getenv(name, "0").strip().lower()
            if value not in {"0", "1", "false", "true"}:
                raise ValueError(name + " must be 0 or 1")
            return value in {"1", "true"}
        return cls(
            api_key=os.getenv("CAUSALGATE_API_KEY", ""),
            policy_path=os.getenv("CAUSALGATE_API_POLICY_PATH") or None,
            audit_log_path=os.getenv("CAUSALGATE_API_AUDIT_LOG") or None,
            enable_tool_guard=flag("CAUSALGATE_API_ENABLE_TOOL_GUARD"),
            enable_docs=flag("CAUSALGATE_API_ENABLE_DOCS"),
            requests_per_minute=int(os.getenv("CAUSALGATE_API_REQUESTS_PER_MINUTE", "60")),
            max_body_bytes=int(os.getenv("CAUSALGATE_API_MAX_BODY_BYTES", "65536")),
            body_timeout_seconds=float(os.getenv("CAUSALGATE_API_BODY_TIMEOUT_SECONDS", "10")),
        )


class RateLimiter:
    """One bounded, process-local rolling window, shared by all authenticated callers."""
    def __init__(self, limit, clock=time.monotonic):
        self.limit, self.clock = limit, clock
        self.hits = deque()
        self.lock = Lock()

    def allow(self):
        now = self.clock()
        with self.lock:
            while self.hits and self.hits[0] <= now - 60:
                self.hits.popleft()
            if len(self.hits) >= self.limit:
                return False
            self.hits.append(now)
            return True


def _object(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key")
        out[key] = value
    return out


def _reject_constant(value):
    raise ValueError("non-finite JSON number")


def validate_json(value, depth=0, budget=None):
    budget = [5000] if budget is None else budget
    budget[0] -= 1
    if depth > 24 or budget[0] < 0:
        raise ValueError("JSON complexity limit exceeded")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    if isinstance(value, dict):
        for child in value.values():
            validate_json(child, depth + 1, budget)
    elif isinstance(value, list):
        for child in value:
            validate_json(child, depth + 1, budget)


class APISecurityMiddleware:
    """Check auth before buffering, then enforce streaming body size and deadline."""
    def __init__(self, app, settings):
        self.app, self.settings = app, settings
        self.limiter = RateLimiter(settings.requests_per_minute)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def reply(status, detail, extra=()):
            body = json.dumps({"detail": detail}).encode()
            await send({"type": "http.response.start", "status": status, "headers": [
                (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"), *extra]})
            await send({"type": "http.response.body", "body": body})

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message = {**message, "headers": list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff")]}
            await send(message)

        if scope["path"] in {"/", "/v1/health", "/v1/ready"} and scope["method"] in {"GET", "HEAD"}:
            return await self.app(scope, receive, secure_send)
        if not self.settings.api_key:
            return await reply(503, "API authentication is not configured")
        auth = [v for k, v in scope.get("headers", []) if k.lower() == b"authorization"]
        expected = ("Bearer " + self.settings.api_key).encode("ascii")
        if len(auth) != 1 or not hmac.compare_digest(auth[0], expected):
            return await reply(401, "Invalid or missing bearer token", [(b"www-authenticate", b"Bearer")])
        if not self.limiter.allow():
            return await reply(429, "Request limit exceeded", [(b"retry-after", b"60")])
        if scope["method"] not in {"POST", "PUT", "PATCH"}:
            return await self.app(scope, receive, secure_send)
        headers = scope.get("headers", [])
        lengths = [v for k, v in headers if k.lower() == b"content-length"]
        try:
            if len(lengths) > 1 or (lengths and int(lengths[0]) < 0):
                return await reply(400, "Invalid content length")
            if lengths and int(lengths[0]) > self.settings.max_body_bytes:
                return await reply(413, "Request body too large")
        except ValueError:
            return await reply(400, "Invalid content length")
        types = [v for k, v in headers if k.lower() == b"content-type"]
        if len(types) != 1 or types[0].split(b";", 1)[0].strip().lower() != b"application/json":
            return await reply(415, "Content-Type must be application/json")
        body = bytearray()

        async def read_body():
            while True:
                event = await receive()
                if event["type"] == "http.disconnect":
                    raise ValueError("Client disconnected")
                chunk = event.get("body", b"")
                if len(body) + len(chunk) > self.settings.max_body_bytes:
                    return False
                body.extend(chunk)
                if not event.get("more_body", False):
                    return True
        try:
            complete = await asyncio.wait_for(read_body(), self.settings.body_timeout_seconds)
        except asyncio.TimeoutError:
            return await reply(408, "Request body timeout")
        except ValueError:
            return await reply(400, "Incomplete request body")
        if not complete:
            return await reply(413, "Request body too large")
        try:
            payload = json.loads(body, object_pairs_hook=_object, parse_constant=_reject_constant)
            validate_json(payload)
        except (ValueError, RecursionError, UnicodeError):
            return await reply(422, "Invalid JSON or complexity limit exceeded")
        if not isinstance(payload, dict):
            return await reply(422, "Request body must be a JSON object")
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, replay, secure_send)
