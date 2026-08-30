import json

import pytest
from ask_sdk_model.request_envelope import RequestEnvelope

from studylife_alexa import handlers
from studylife_alexa.oauth_store import OAuthStore


def _intent_envelope(intent_name: str, *, access_token: str | None) -> dict:
    return {
        "version": "1.0",
        "session": {
            "new": False,
            "sessionId": "amzn1.echo-api.session.test",
            "application": {"applicationId": "amzn1.ask.skill.test"},
            "user": {"userId": "amzn1.ask.account.test"},
        },
        "context": {
            "System": {
                "application": {"applicationId": "amzn1.ask.skill.test"},
                "user": {"userId": "amzn1.ask.account.test", "accessToken": access_token},
                "apiEndpoint": "https://api.eu.amazonalexa.com",
            }
        },
        "request": {
            "type": "IntentRequest",
            "requestId": "amzn1.echo-api.request.test",
            "timestamp": "2026-08-30T12:00:00Z",
            "locale": "de-DE",
            "intent": {"name": intent_name, "confirmationStatus": "NONE"},
        },
    }


def _invoke(intent_name: str, *, access_token: str | None) -> dict:
    from studylife_alexa.main import _skill

    request_envelope = _skill.serializer.deserialize(
        payload=json.dumps(_intent_envelope(intent_name, access_token=access_token)),
        obj_type=RequestEnvelope,
    )
    response_envelope = _skill.invoke(request_envelope, context=None)
    return _skill.serializer.serialize(response_envelope)


def _speech(response_body: dict) -> str:
    return response_body["response"]["outputSpeech"]["ssml"]


def test_courses_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("CoursesIntent", access_token=None)

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_courses_intent_with_linked_account_calls_studylife(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from studylife_alexa.config import Settings

    settings = Settings()  # type: ignore[call-arg]
    store = OAuthStore(settings.alexa_oauth_db_path, settings.alexa_token_encryption_key or "")
    await store.initialize()
    await store.save_access_token("real-alexa-access-token", "fake-studylife-api-key")

    monkeypatch.setattr(
        handlers, "list_courses_sync", lambda base_url, api_key: [{"id": 1}, {"id": 2}]
    )

    body = _invoke("CoursesIntent", access_token="real-alexa-access-token")

    assert "2 Kurse" in _speech(body)
