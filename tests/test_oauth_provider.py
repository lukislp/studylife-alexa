from urllib.parse import parse_qs, urlparse

import pytest

from studylife_alexa import oauth_provider
from studylife_alexa.client import ExchangedAssertion
from studylife_alexa.main import app

ALEXA_CLIENT_ID = "test-alexa-client-id"
ALEXA_CLIENT_SECRET = "test-alexa-client-secret"
ALEXA_REDIRECT_URI = "https://pitangui.amazon.com/api/skill/link/TEST"
CHOSEN_INSTANCE_URL = "https://my-own-studylife.example.net"


def _authorize_params(**overrides: str) -> dict[str, str]:
    params = {
        "response_type": "code",
        "client_id": ALEXA_CLIENT_ID,
        "redirect_uri": ALEXA_REDIRECT_URI,
        "state": "alexa-state-123",
    }
    params.update(overrides)
    return params


async def _fake_reachable(instance_url: str) -> bool:
    return True


async def _fake_unreachable(instance_url: str) -> bool:
    return False


def test_authorize_without_instance_url_shows_instance_form(client) -> None:
    response = client.get("/authorize", params=_authorize_params(), follow_redirects=False)

    assert response.status_code == 200
    assert 'name="instance_url"' in response.text
    # Alexa's own params must survive as hidden fields for the form's own follow-up
    # submission - dropping any of them here would break the round trip.
    assert 'name="state" value="alexa-state-123"' in response.text
    assert f'name="redirect_uri" value="{ALEXA_REDIRECT_URI}"' in response.text


def test_authorize_escapes_reflected_values_in_instance_form(client) -> None:
    """Regression: state/instance_url are attacker-influenceable query params reflected
    straight into the instance-selection form's HTML - the form must HTML-escape them,
    or this is a reflected-XSS hole."""
    payload = '"><script>alert(1)</script>'
    response = client.get(
        "/authorize",
        params=_authorize_params(state=payload, instance_url=payload),
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_authorize_rejects_non_https_instance_url(client) -> None:
    response = client.get(
        "/authorize",
        params=_authorize_params(instance_url="http://insecure.example.com"),
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "must start with https" in response.text


def test_authorize_shows_error_when_instance_unreachable(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oauth_provider, "_verify_instance_reachable", _fake_unreachable)

    response = client.get(
        "/authorize",
        params=_authorize_params(instance_url=CHOSEN_INSTANCE_URL),
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert "Could not reach" in response.text


def test_authorize_redirects_to_studylife_connect(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth_provider, "_verify_instance_reachable", _fake_reachable)

    response = client.get(
        "/authorize",
        params=_authorize_params(instance_url=CHOSEN_INSTANCE_URL),
        follow_redirects=False,
    )

    assert response.status_code == 302
    location = urlparse(response.headers["location"])
    assert f"{location.scheme}://{location.netloc}" == CHOSEN_INSTANCE_URL
    assert location.path == "/connect/client/studylife-alexa"
    query = parse_qs(location.query)
    assert query["redirect_uri"] == ["https://studylife-alexa.example.com/oauth/studylife/callback"]
    assert "state" in query


def test_authorize_rejects_wrong_client_id(client) -> None:
    response = client.get(
        "/authorize", params=_authorize_params(client_id="someone-else"), follow_redirects=False
    )
    assert response.status_code == 401


def test_authorize_accepts_any_configured_regional_redirect_uri(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(oauth_provider, "_verify_instance_reachable", _fake_reachable)
    japan_redirect_uri = "https://alexa.amazon.co.jp/api/skill/link/TEST"

    response = client.get(
        "/authorize",
        params=_authorize_params(redirect_uri=japan_redirect_uri, instance_url=CHOSEN_INSTANCE_URL),
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


async def test_full_round_trip_authorize_to_token(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth_provider, "_verify_instance_reachable", _fake_reachable)
    monkeypatch.setattr(oauth_provider, "exchange_assertion", _fake_exchange_assertion)

    # Step 1: Alexa sends the browser to /authorize, having already chosen an instance.
    authorize_response = client.get(
        "/authorize",
        params=_authorize_params(instance_url=CHOSEN_INSTANCE_URL),
        follow_redirects=False,
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

    # The issued access token must resolve back to the SAME instance the user chose in
    # step 1, not some other/default one - this is the whole point of the multi-tenant
    # instance-selection form.
    from studylife_alexa.config import Settings
    from studylife_alexa.oauth_store import OAuthStore

    settings = Settings()  # type: ignore[call-arg]
    store = OAuthStore(settings.alexa_oauth_db_path, settings.alexa_token_encryption_key or "")
    linked = await store.load_access_token(body["access_token"])
    assert linked is not None
    assert linked.base_url == CHOSEN_INSTANCE_URL
    assert linked.api_key == "fake-studylife-api-key"

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
    assert base_url == CHOSEN_INSTANCE_URL
    assert assertion == "fake-assertion"
    return ExchangedAssertion(user_id=1, api_key="fake-studylife-api-key")


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
