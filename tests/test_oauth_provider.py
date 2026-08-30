from urllib.parse import parse_qs, urlparse

import pytest

from studylife_alexa import oauth_provider
from studylife_alexa.client import ExchangedAssertion
from studylife_alexa.main import app

ALEXA_CLIENT_ID = "test-alexa-client-id"
ALEXA_CLIENT_SECRET = "test-alexa-client-secret"
ALEXA_REDIRECT_URI = "https://pitangui.amazon.com/api/skill/link/TEST"


def _authorize_params(**overrides: str) -> dict[str, str]:
    params = {
        "response_type": "code",
        "client_id": ALEXA_CLIENT_ID,
        "redirect_uri": ALEXA_REDIRECT_URI,
        "state": "alexa-state-123",
    }
    params.update(overrides)
    return params


def test_authorize_redirects_to_studylife_connect(client) -> None:
    response = client.get("/authorize", params=_authorize_params(), follow_redirects=False)

    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert location.netloc == "studylife.example.com"
    assert location.path == "/connect/client/studylife-alexa"
    query = parse_qs(location.query)
    assert query["redirect_uri"] == ["https://studylife-alexa.example.com/oauth/studylife/callback"]
    assert "state" in query


def test_authorize_rejects_wrong_client_id(client) -> None:
    response = client.get(
        "/authorize", params=_authorize_params(client_id="someone-else"), follow_redirects=False
    )
    assert response.status_code == 401


def test_authorize_accepts_any_configured_regional_redirect_uri(client) -> None:
    japan_redirect_uri = "https://alexa.amazon.co.jp/api/skill/link/TEST"
    response = client.get(
        "/authorize",
        params=_authorize_params(redirect_uri=japan_redirect_uri),
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_authorize_rejects_wrong_redirect_uri(client) -> None:
    response = client.get(
        "/authorize",
        params=_authorize_params(redirect_uri="https://evil.example.com/callback"),
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_full_round_trip_authorize_to_token(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        oauth_provider,
        "exchange_assertion",
        _fake_exchange_assertion,
    )

    # Step 1: Alexa sends the browser to /authorize.
    authorize_response = client.get(
        "/authorize", params=_authorize_params(), follow_redirects=False
    )
    our_state = parse_qs(urlparse(authorize_response.headers["location"]).query)["state"][0]

    # Step 2: StudyLife's connect flow redirects back with our own state + an assertion.
    callback_response = client.get(
        "/oauth/studylife/callback",
        params={"state": our_state, "assertion": "fake-assertion"},
        follow_redirects=False,
    )
    assert callback_response.status_code == 302
    callback_location = urlparse(callback_response.headers["location"])
    assert f"{callback_location.scheme}://{callback_location.netloc}{callback_location.path}" == (
        ALEXA_REDIRECT_URI
    )
    callback_query = parse_qs(callback_location.query)
    assert callback_query["state"] == ["alexa-state-123"]
    code = callback_query["code"][0]

    # Step 3: Alexa's backend exchanges the code for an access token.
    token_response = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": ALEXA_CLIENT_ID,
            "client_secret": ALEXA_CLIENT_SECRET,
        },
    )
    assert token_response.status_code == 200
    body = token_response.json()
    assert body["token_type"] == "Bearer"
    assert "access_token" in body
    assert "refresh_token" in body

    # The authorization code is single-use.
    replay_response = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": ALEXA_CLIENT_ID,
            "client_secret": ALEXA_CLIENT_SECRET,
        },
    )
    assert replay_response.status_code == 400


def test_token_rejects_wrong_client_secret(client, monkeypatch: pytest.MonkeyPatch) -> None:
    response = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": "irrelevant",
            "client_id": ALEXA_CLIENT_ID,
            "client_secret": "wrong-secret",
        },
    )
    assert response.status_code == 401


async def _fake_exchange_assertion(base_url: str, assertion: str) -> ExchangedAssertion | None:
    assert assertion == "fake-assertion"
    return ExchangedAssertion(user_id=1, api_key="fake-studylife-api-key")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
