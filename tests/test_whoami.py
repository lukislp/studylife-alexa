"""client.whoami: the user id behind an API key, and what counts as a rejected key."""

from __future__ import annotations

import httpx
import pytest

from studylife_alexa import client


def _serve(monkeypatch: pytest.MonkeyPatch, handler) -> list[httpx.Request]:
    seen: list[httpx.Request] = []
    real = httpx.AsyncClient

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    monkeypatch.setattr(
        client.httpx,
        "AsyncClient",
        lambda **kwargs: real(transport=httpx.MockTransport(recording), **kwargs),
    )
    return seen


async def test_whoami_returns_the_user_id(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _serve(monkeypatch, lambda r: httpx.Response(200, json={"userId": 7, "credential": "x"}))

    owner = await client.whoami("https://study.example/", "the-key")

    assert owner.user_id == 7 and not owner.rejected
    assert str(seen[0].url) == "https://study.example/api/auth/whoami"
    assert seen[0].headers["X-Api-Key"] == "the-key"


async def test_whoami_401_means_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, lambda r: httpx.Response(401))

    owner = await client.whoami("https://study.example", "dead-key")

    assert owner.rejected and owner.user_id is None


@pytest.mark.parametrize(
    "response",
    [httpx.Response(503), httpx.Response(200, json={"nope": 1}), httpx.Response(200, text="x")],
)
async def test_whoami_other_failures_are_neither_id_nor_rejection(
    monkeypatch: pytest.MonkeyPatch, response: httpx.Response
) -> None:
    _serve(monkeypatch, lambda r: response)

    owner = await client.whoami("https://study.example", "key")

    assert owner.user_id is None and not owner.rejected


async def test_whoami_transport_error_is_not_a_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    _serve(monkeypatch, boom)

    owner = await client.whoami("https://study.example", "key")

    assert owner.user_id is None and not owner.rejected
