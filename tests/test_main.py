from fastapi.testclient import TestClient

from studylife_alexa.main import app

client = TestClient(app)


def _request_envelope(request_type: str, intent_name: str | None = None) -> dict:
    request = {
        "type": request_type,
        "requestId": "amzn1.echo-api.request.test",
        "timestamp": "2026-08-30T12:00:00Z",
        "locale": "de-DE",
    }
    if intent_name is not None:
        request["intent"] = {"name": intent_name, "confirmationStatus": "NONE"}

    return {
        "version": "1.0",
        "session": {
            "new": True,
            "sessionId": "amzn1.echo-api.session.test",
            "application": {"applicationId": "amzn1.ask.skill.test"},
            "user": {"userId": "amzn1.ask.account.test"},
        },
        "context": {
            "System": {
                "application": {"applicationId": "amzn1.ask.skill.test"},
                "user": {"userId": "amzn1.ask.account.test"},
                "apiEndpoint": "https://api.eu.amazonalexa.com",
            }
        },
        "request": request,
    }


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_launch_request_responds_with_welcome_speech() -> None:
    response = client.post("/alexa/skill", json=_request_envelope("LaunchRequest"))

    assert response.status_code == 200
    body = response.json()
    assert "Willkommen" in body["response"]["outputSpeech"]["ssml"]
    assert body["response"]["shouldEndSession"] is False


def test_test_intent_confirms_connection() -> None:
    envelope = _request_envelope("IntentRequest", intent_name="TestIntent")
    response = client.post("/alexa/skill", json=envelope)

    assert response.status_code == 200
    body = response.json()
    assert "Verbindung funktioniert" in body["response"]["outputSpeech"]["ssml"]


def test_stop_intent_ends_session() -> None:
    envelope = _request_envelope("IntentRequest", intent_name="AMAZON.StopIntent")
    response = client.post("/alexa/skill", json=envelope)

    assert response.status_code == 200
    body = response.json()
    assert body["response"]["shouldEndSession"] is True


def test_wrong_skill_id_is_rejected() -> None:
    envelope = _request_envelope("LaunchRequest")
    envelope["context"]["System"]["application"]["applicationId"] = "amzn1.ask.skill.other"

    response = client.post("/alexa/skill", json=envelope)

    assert response.status_code == 403
