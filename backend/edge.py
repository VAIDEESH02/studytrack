"""Protections that run before any route: security headers, the Netlify origin lock, and a body cap.

In production the browser reaches the API only through the Netlify ``/api`` proxy. Netlify signs
every proxied request with a short-lived HS256 JSON Web Signature in the ``x-nf-sign`` header,
using the secret stored in its ``PROXY_SIGNING_SECRET`` environment variable (see netlify.toml).
When the API has the same secret, it refuses every unsigned request with a cheap 403 before any
database or password-hashing work. Calling the Render URL directly therefore gets nowhere, and
Netlify's per-IP rate limits cannot be bypassed.
"""

from __future__ import annotations

import json
import os

import jwt
from fastapi import Request
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from . import auth

SIGNATURE_HEADER = b"x-nf-sign"
CLIENT_IP_HEADER = b"x-nf-client-connection-ip"
SIGNATURE_LEEWAY_SECONDS = 30
# Render's health checks and the deploy workflow call /health directly, not through Netlify.
UNSIGNED_PATHS = {"/health"}
MAX_BODY_BYTES = 256 * 1024
NOT_FROM_PROXY = "Requests must come through the StudyTrack site"
BODY_TOO_LARGE = "Request body is too large"


def proxy_signing_secret() -> str:
    return os.getenv("PROXY_SIGNING_SECRET", "").strip()


def trusted_client_ip(request: Request) -> str | None:
    """The visitor's IP as reported by Netlify, available only on signed requests."""
    return request.scope.get("state", {}).get("client_ip")


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return None


async def _send_json(send: Send, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        }
    )
    await send({"type": "http.response.body", "body": body})


def is_valid_proxy_signature(token: str, secret: str) -> bool:
    """True for an unexpired token Netlify signed for a production deploy of the site."""
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer="netlify",
            leeway=SIGNATURE_LEEWAY_SECONDS,
            options={"require": ["exp", "iss"]},
        )
    except jwt.InvalidTokenError:
        return False
    # Deploy previews and branch deploys carry another context; they must never reach production data.
    return claims.get("deploy_context") == "production"


class SecurityHeadersMiddleware:
    """Stamp every API response, including 403s and 413s from the other middlewares."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        extra = [
            (b"cache-control", b"no-store"),
            (b"x-content-type-options", b"nosniff"),
            (b"referrer-policy", b"no-referrer"),
            (b"x-frame-options", b"DENY"),
        ]
        if auth.is_production():
            extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
        replaced = {name for name, _ in extra}

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                kept = [(key, value) for key, value in message.get("headers", []) if key.lower() not in replaced]
                message["headers"] = [*kept, *extra]
            await send(message)

        await self.app(scope, receive, send_with_headers)


class ProxySignatureMiddleware:
    """Origin lock: only requests signed by the Netlify proxy get through (when a secret is set)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        secret = proxy_signing_secret()
        if scope["type"] != "http" or not secret:
            await self.app(scope, receive, send)
            return
        if scope["path"] in UNSIGNED_PATHS and scope["method"] in {"GET", "HEAD"}:
            await self.app(scope, receive, send)
            return
        token = _header(scope, SIGNATURE_HEADER)
        if not token or not is_valid_proxy_signature(token, secret):
            await _send_json(send, 403, NOT_FROM_PROXY)
            return
        client_ip = _header(scope, CLIENT_IP_HEADER)
        if client_ip:
            scope.setdefault("state", {})["client_ip"] = client_ip
        await self.app(scope, receive, send)


class BodySizeLimitMiddleware:
    """Refuse request bodies over the limit, whether or not the client declares a Content-Length."""

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        declared = _header(scope, b"content-length")
        if declared is not None:
            try:
                too_large = int(declared) > self.max_bytes
            except ValueError:
                await _send_json(send, 400, "Invalid Content-Length header")
                return
            if too_large:
                await _send_json(send, 413, BODY_TOO_LARGE)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    # FastAPI re-raises HTTPExceptions from body reading, so this becomes a 413 response.
                    raise HTTPException(status_code=413, detail=BODY_TOO_LARGE)
            return message

        await self.app(scope, limited_receive, send)
