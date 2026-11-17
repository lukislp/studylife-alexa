"""Audit 2026-11-16 L23: the public /authorize endpoint must not be usable to make this
server request internal addresses."""

from __future__ import annotations

import httpx
import pytest

from studylife_alexa import instance_guard, oauth_provider
from studylife_alexa.instance_guard import (
    is_acceptable_instance_url,
    is_host_allowed,
    parse_allowed_hosts,
    resolves_to_public_addresses_only,
)


def _fake_getaddrinfo(*addresses: str):
    async def fake(host, port, **kwargs):
        return [(0, 0, 0, "", (address, port)) for address in addresses]

    return fake


async def _resolve(monkeypatch: pytest.MonkeyPatch, url: str, *addresses: str) -> bool:
    loop = instance_guard.asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", _fake_getaddrinfo(*addresses))
    return await resolves_to_public_addresses_only(url)


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.10",
        "172.16.0.1",
        "169.254.169.254",
        "100.64.0.1",
        "0.0.0.0",
        "::1",
        "fe80::1",
        "fd00::1",
        "::ffff:10.0.0.1",
    ],
)
async def test_non_public_addresses_are_refused(monkeypatch, address: str) -> None:
    assert await _resolve(monkeypatch, "https://study.example.net", address) is False


async def test_mixed_public_and_private_answers_are_refused(monkeypatch) -> None:
    assert (
        await _resolve(monkeypatch, "https://study.example.net", "93.184.216.34", "10.0.0.1")
        is False
    )


async def test_public_addresses_are_accepted(monkeypatch) -> None:
    assert await _resolve(monkeypatch, "https://study.example.net", "93.184.216.34") is True
    assert await _resolve(monkeypatch, "https://study.example.net", "2606:2800:220:1::1") is True


async def test_unresolvable_host_is_refused() -> None:
    assert await resolves_to_public_addresses_only("https://does-not-exist.invalid") is False


@pytest.mark.parametrize(
    ("url", "ok"),
    [
        ("https://study.example.net", True),
        ("https://study.example.net:8443/app", True),
        ("http://study.example.net", False),
        ("https://user:pw@study.example.net", False),
        ("https://study.example.net?x=1", False),
        ("https://study.example.net#frag", False),
        ("https://study.example.net:notaport", False),
        ("https://", False),
    ],
)
def test_instance_url_syntax(url: str, ok: bool) -> None:
    assert is_acceptable_instance_url(url) is ok


def test_allow_list() -> None:
    allowed = parse_allowed_hosts(" Study.Example.net , other.example.org ,")
    assert is_host_allowed("https://study.example.net", allowed)
    assert is_host_allowed("https://other.example.org:8443", allowed)
    assert not is_host_allowed("https://evil.example.net", allowed)
    assert is_host_allowed("https://anything.example.net", parse_allowed_hosts(None))


def _client_with(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    real = httpx.AsyncClient
    monkeypatch.setattr(
        oauth_provider.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )


async def _public(url: str) -> bool:
    return True


async def test_verify_accepts_a_version_response(monkeypatch) -> None:
    monkeypatch.setattr(oauth_provider, "resolves_to_public_addresses_only", _public)
    _client_with(monkeypatch, lambda request: httpx.Response(200, json={"version": "1.2.3"}))
    assert await oauth_provider._verify_instance_reachable("https://study.example.net") is True


async def test_verify_never_connects_to_non_public_hosts(monkeypatch) -> None:
    async def private(url: str) -> bool:
        return False

    def boom(request):
        raise AssertionError("must not send a request")

    monkeypatch.setattr(oauth_provider, "resolves_to_public_addresses_only", private)
    _client_with(monkeypatch, boom)
    assert await oauth_provider._verify_instance_reachable("https://internal.example.net") is False


async def test_verify_does_not_follow_redirects(monkeypatch) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest"})

    monkeypatch.setattr(oauth_provider, "resolves_to_public_addresses_only", _public)
    _client_with(monkeypatch, handler)
    assert await oauth_provider._verify_instance_reachable("https://study.example.net") is False
    assert seen == ["https://study.example.net/api/system/version"]


async def test_verify_rejects_oversized_response(monkeypatch) -> None:
    body = b'{"version": "1", "pad": "' + b"x" * 10_000 + b'"}'
    monkeypatch.setattr(oauth_provider, "resolves_to_public_addresses_only", _public)
    _client_with(monkeypatch, lambda request: httpx.Response(200, content=body))
    assert await oauth_provider._verify_instance_reachable("https://study.example.net") is False


async def test_verify_rejects_non_json_body(monkeypatch) -> None:
    monkeypatch.setattr(oauth_provider, "resolves_to_public_addresses_only", _public)
    _client_with(monkeypatch, lambda request: httpx.Response(200, content=b"<html>"))
    assert await oauth_provider._verify_instance_reachable("https://study.example.net") is False


def test_authorize_rejects_host_not_on_allow_list(tmp_path) -> None:
    from cryptography.fernet import Fernet
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from studylife_alexa.config import Settings
    from studylife_alexa.oauth_store import OAuthStore

    settings = Settings(alexa_allowed_instance_hosts="only.example.org")  # type: ignore[call-arg]
    store = OAuthStore(str(tmp_path / "oauth.db"), Fernet.generate_key().decode())
    app = FastAPI()
    oauth_provider.register_oauth_routes(app, store, settings)

    with TestClient(app) as http:
        response = http.get(
            "/authorize",
            params={
                "response_type": "code",
                "client_id": "test-alexa-client-id",
                "redirect_uri": "https://pitangui.amazon.com/api/skill/link/TEST",
                "state": "s",
                "instance_url": "https://other.example.net",
            },
            follow_redirects=False,
        )
    assert response.status_code == 200
    assert "approved instances" in response.text
