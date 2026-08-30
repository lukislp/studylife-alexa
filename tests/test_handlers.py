import json
from datetime import datetime, timedelta

import pytest
from ask_sdk_model.request_envelope import RequestEnvelope

from studylife_alexa import handlers
from studylife_alexa.oauth_store import OAuthStore


def _intent_envelope(
    intent_name: str, *, access_token: str | None, slots: dict[str, str] | None = None
) -> dict:
    intent: dict = {"name": intent_name, "confirmationStatus": "NONE"}
    if slots is not None:
        intent["slots"] = {
            slot_name: {"name": slot_name, "value": slot_value, "confirmationStatus": "NONE"}
            for slot_name, slot_value in slots.items()
        }
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
            "intent": intent,
        },
    }


def _invoke(
    intent_name: str, *, access_token: str | None, slots: dict[str, str] | None = None
) -> dict:
    from studylife_alexa.main import _skill

    request_envelope = _skill.serializer.deserialize(
        payload=json.dumps(_intent_envelope(intent_name, access_token=access_token, slots=slots)),
        obj_type=RequestEnvelope,
    )
    response_envelope = _skill.invoke(request_envelope, context=None)
    return _skill.serializer.serialize(response_envelope)


def _speech(response_body: dict) -> str:
    return response_body["response"]["outputSpeech"]["ssml"]


async def _link_account(access_token: str, api_key: str) -> None:
    from studylife_alexa.config import Settings

    settings = Settings()  # type: ignore[call-arg]
    store = OAuthStore(settings.alexa_oauth_db_path, settings.alexa_token_encryption_key or "")
    await store.initialize()
    await store.save_access_token(access_token, api_key)


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
    # Regression: a successful answer must keep the session open (a follow-up question
    # shouldn't need "Alexa, öffne study life" said again) - shouldEndSession is only
    # present in the JSON at all once something (like .ask()) actually sets it.
    assert body["response"]["shouldEndSession"] is False


# ---------------------------------------------------------------------------
# TimerStatusIntent
# ---------------------------------------------------------------------------


def test_timer_status_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("TimerStatusIntent", access_token=None)

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_timer_status_intent_not_running(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("timer-token-not-running", "fake-api-key")
    monkeypatch.setattr(
        handlers, "get_timer_state_sync", lambda base_url, api_key: {"isRunning": False}
    )

    body = _invoke("TimerStatusIntent", access_token="timer-token-not-running")

    assert "Gerade läuft kein Fokus-Timer." in _speech(body)


async def test_timer_status_intent_running_in_break(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("timer-token-break", "fake-api-key")
    monkeypatch.setattr(
        handlers,
        "get_timer_state_sync",
        lambda base_url, api_key: {"isRunning": True, "isBreak": True},
    )

    body = _invoke("TimerStatusIntent", access_token="timer-token-break")

    assert "Pause" in _speech(body)


async def test_timer_status_intent_running_focused(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("timer-token-focused", "fake-api-key")
    monkeypatch.setattr(
        handlers,
        "get_timer_state_sync",
        lambda base_url, api_key: {"isRunning": True, "isBreak": False},
    )

    body = _invoke("TimerStatusIntent", access_token="timer-token-focused")

    assert "Dein Fokus-Timer läuft gerade." in _speech(body)


async def test_timer_status_intent_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("timer-token-unreachable", "fake-api-key")

    def _raise(base_url: str, api_key: str) -> dict:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "get_timer_state_sync", _raise)

    body = _invoke("TimerStatusIntent", access_token="timer-token-unreachable")

    assert handlers._STUDYLIFE_UNREACHABLE_SPEECH in _speech(body)


# ---------------------------------------------------------------------------
# StudyTimeIntent
# ---------------------------------------------------------------------------


def test_study_time_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("StudyTimeIntent", access_token=None, slots={"TimePeriod": "heute"})

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_study_time_intent_today_under_an_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("study-time-token-today", "fake-api-key")
    recorded_days: list[int | None] = []

    start = datetime.now() - timedelta(hours=2)
    end = start + timedelta(minutes=45)

    def fake_get_session_history_sync(
        base_url: str, api_key: str, days: int | None = None
    ) -> list[dict[str, object]]:
        recorded_days.append(days)
        return [{"startTime": start.isoformat(), "endTime": end.isoformat()}]

    monkeypatch.setattr(handlers, "get_session_history_sync", fake_get_session_history_sync)

    body = _invoke(
        "StudyTimeIntent", access_token="study-time-token-today", slots={"TimePeriod": "heute"}
    )

    assert recorded_days == [1]
    assert "Du hast heute 45 Minuten gelernt." in _speech(body)


async def test_study_time_intent_this_week_over_an_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("study-time-token-week", "fake-api-key")
    recorded_days: list[int | None] = []

    first_start = datetime.now() - timedelta(days=2)
    second_start = datetime.now() - timedelta(days=3)

    def fake_get_session_history_sync(
        base_url: str, api_key: str, days: int | None = None
    ) -> list[dict[str, object]]:
        recorded_days.append(days)
        return [
            {
                "startTime": first_start.isoformat(),
                "endTime": (first_start + timedelta(minutes=90)).isoformat(),
            },
            {
                "startTime": second_start.isoformat(),
                "endTime": (second_start + timedelta(minutes=60)).isoformat(),
            },
        ]

    monkeypatch.setattr(handlers, "get_session_history_sync", fake_get_session_history_sync)

    body = _invoke(
        "StudyTimeIntent", access_token="study-time-token-week", slots={"TimePeriod": "diese Woche"}
    )

    assert recorded_days == [7]
    assert "Du hast diese Woche 2 Stunden und 30 Minuten gelernt." in _speech(body)


async def test_study_time_intent_last_week_excludes_this_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: "letzte Woche" (last week) was previously matched against the same
    synonym list as "diese Woche" (this week) in the interaction model, so both fetched
    the trailing 7 days unfiltered. A session from 2 days ago (this week) must NOT be
    counted, and a session from 10 days ago (last week) must be."""
    await _link_account("study-time-token-last-week", "fake-api-key")
    recorded_days: list[int | None] = []
    this_week_start = datetime.now() - timedelta(days=2)
    last_week_start = datetime.now() - timedelta(days=10)

    def fake_get_session_history_sync(
        base_url: str, api_key: str, days: int | None = None
    ) -> list[dict[str, object]]:
        recorded_days.append(days)
        return [
            {
                "startTime": this_week_start.isoformat(),
                "endTime": (this_week_start + timedelta(hours=5)).isoformat(),
            },
            {
                "startTime": last_week_start.isoformat(),
                "endTime": (last_week_start + timedelta(minutes=30)).isoformat(),
            },
        ]

    monkeypatch.setattr(handlers, "get_session_history_sync", fake_get_session_history_sync)

    body = _invoke(
        "StudyTimeIntent",
        access_token="study-time-token-last-week",
        slots={"TimePeriod": "letzte Woche"},
    )

    assert recorded_days == [14]
    assert "Du hast letzte Woche 30 Minuten gelernt." in _speech(body)


async def test_study_time_intent_this_month_no_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("study-time-token-month", "fake-api-key")
    recorded_days: list[int | None] = []

    def fake_get_session_history_sync(
        base_url: str, api_key: str, days: int | None = None
    ) -> list[dict[str, object]]:
        recorded_days.append(days)
        return []

    monkeypatch.setattr(handlers, "get_session_history_sync", fake_get_session_history_sync)

    body = _invoke(
        "StudyTimeIntent",
        access_token="study-time-token-month",
        slots={"TimePeriod": "diesen Monat"},
    )

    assert recorded_days == [30]
    assert "Du hast diesen Monat noch nicht gelernt." in _speech(body)


async def test_study_time_intent_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("study-time-token-unreachable", "fake-api-key")

    def _raise(base_url: str, api_key: str, days: int | None = None) -> list[dict[str, object]]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "get_session_history_sync", _raise)

    body = _invoke(
        "StudyTimeIntent",
        access_token="study-time-token-unreachable",
        slots={"TimePeriod": "heute"},
    )

    assert handlers._STUDYLIFE_UNREACHABLE_SPEECH in _speech(body)


# ---------------------------------------------------------------------------
# RecentSessionsIntent
# ---------------------------------------------------------------------------


def test_recent_sessions_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("RecentSessionsIntent", access_token=None)

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_recent_sessions_intent_with_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("recent-sessions-token", "fake-api-key")
    recorded_days: list[int | None] = []

    def fake_get_session_history_sync(
        base_url: str, api_key: str, days: int | None = None
    ) -> list[dict[str, object]]:
        recorded_days.append(days)
        return [
            {"courseName": "Analysis"},
            {"courseName": "Lineare Algebra"},
            {"courseName": "Statistik"},
        ]

    monkeypatch.setattr(handlers, "get_session_history_sync", fake_get_session_history_sync)

    body = _invoke("RecentSessionsIntent", access_token="recent-sessions-token")

    assert recorded_days == [7]
    speech = _speech(body)
    assert "3 Lernsessions" in speech
    assert "Analysis, Lineare Algebra, Statistik" in speech


async def test_recent_sessions_intent_with_no_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("recent-sessions-token-empty", "fake-api-key")
    monkeypatch.setattr(
        handlers, "get_session_history_sync", lambda base_url, api_key, days=None: []
    )

    body = _invoke("RecentSessionsIntent", access_token="recent-sessions-token-empty")

    assert "Du hast in den letzten sieben Tagen keine Lernsessions gehabt." in _speech(body)


async def test_recent_sessions_intent_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("recent-sessions-token-unreachable", "fake-api-key")

    def _raise(base_url: str, api_key: str, days: int | None = None) -> list[dict[str, object]]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "get_session_history_sync", _raise)

    body = _invoke("RecentSessionsIntent", access_token="recent-sessions-token-unreachable")

    assert handlers._STUDYLIFE_UNREACHABLE_SPEECH in _speech(body)


# ---------------------------------------------------------------------------
# CourseGoalsIntent
# ---------------------------------------------------------------------------


def test_course_goals_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("CourseGoalsIntent", access_token=None)

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_course_goals_intent_with_open_and_completed_goals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("course-goals-token", "fake-api-key")
    monkeypatch.setattr(
        handlers,
        "list_course_goals_sync",
        lambda base_url, api_key: [
            {"id": 1, "completedAt": None},
            {"id": 2, "completedAt": "2026-08-20T10:00:00"},
            {"id": 3, "completedAt": None},
        ],
    )

    body = _invoke("CourseGoalsIntent", access_token="course-goals-token")

    assert "Du hast 3 Lernziele in StudyLife, davon sind 2 noch offen." in _speech(body)


async def test_course_goals_intent_with_no_goals(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("course-goals-token-empty", "fake-api-key")
    monkeypatch.setattr(handlers, "list_course_goals_sync", lambda base_url, api_key: [])

    body = _invoke("CourseGoalsIntent", access_token="course-goals-token-empty")

    assert "Du hast aktuell keine Lernziele in StudyLife angelegt." in _speech(body)


async def test_course_goals_intent_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("course-goals-token-unreachable", "fake-api-key")

    def _raise(base_url: str, api_key: str) -> list[dict[str, object]]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "list_course_goals_sync", _raise)

    body = _invoke("CourseGoalsIntent", access_token="course-goals-token-unreachable")

    assert handlers._STUDYLIFE_UNREACHABLE_SPEECH in _speech(body)


# ---------------------------------------------------------------------------
# StudyProgramsIntent
# ---------------------------------------------------------------------------


def test_study_programs_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("StudyProgramsIntent", access_token=None)

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_study_programs_intent_with_programs(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("study-programs-token", "fake-api-key")
    monkeypatch.setattr(
        handlers,
        "list_study_programs_sync",
        lambda base_url, api_key: [{"name": "Informatik"}, {"name": "Mathematik"}],
    )

    body = _invoke("StudyProgramsIntent", access_token="study-programs-token")

    assert "Du hast 2 Studiengänge in StudyLife: Informatik, Mathematik." in _speech(body)


async def test_study_programs_intent_with_no_programs(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("study-programs-token-empty", "fake-api-key")
    monkeypatch.setattr(handlers, "list_study_programs_sync", lambda base_url, api_key: [])

    body = _invoke("StudyProgramsIntent", access_token="study-programs-token-empty")

    assert "Du hast aktuell keinen Studiengang in StudyLife angelegt." in _speech(body)


async def test_study_programs_intent_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("study-programs-token-unreachable", "fake-api-key")

    def _raise(base_url: str, api_key: str) -> list[dict[str, object]]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "list_study_programs_sync", _raise)

    body = _invoke("StudyProgramsIntent", access_token="study-programs-token-unreachable")

    assert handlers._STUDYLIFE_UNREACHABLE_SPEECH in _speech(body)


# ---------------------------------------------------------------------------
# SearchNotesIntent
# ---------------------------------------------------------------------------


def test_search_notes_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("SearchNotesIntent", access_token=None, slots={"SearchQuery": "Analysis"})

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_search_notes_intent_empty_query_reprompts_without_calling_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("search-notes-token-empty-query", "fake-api-key")
    called = False

    def _fail_if_called(base_url: str, api_key: str, query: str) -> list[dict[str, object]]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(handlers, "search_notes_sync", _fail_if_called)

    body = _invoke(
        "SearchNotesIntent",
        access_token="search-notes-token-empty-query",
        slots={"SearchQuery": ""},
    )

    assert not called
    assert "Wonach genau soll ich in deinen Notizen suchen?" in _speech(body)
    assert body["response"]["reprompt"]["outputSpeech"]["ssml"]


async def test_search_notes_intent_missing_slot_reprompts_without_calling_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("search-notes-token-missing-slot", "fake-api-key")
    called = False

    def _fail_if_called(base_url: str, api_key: str, query: str) -> list[dict[str, object]]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(handlers, "search_notes_sync", _fail_if_called)

    body = _invoke("SearchNotesIntent", access_token="search-notes-token-missing-slot")

    assert not called
    assert "Wonach genau soll ich in deinen Notizen suchen?" in _speech(body)


async def test_search_notes_intent_with_results(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("search-notes-token", "fake-api-key")
    recorded_queries: list[str] = []

    def fake_search_notes_sync(base_url: str, api_key: str, query: str) -> list[dict[str, object]]:
        recorded_queries.append(query)
        return [{"title": "Ableitungen"}, {"title": "Integrale"}]

    monkeypatch.setattr(handlers, "search_notes_sync", fake_search_notes_sync)

    body = _invoke(
        "SearchNotesIntent", access_token="search-notes-token", slots={"SearchQuery": "Analysis"}
    )

    assert recorded_queries == ["Analysis"]
    assert (
        "Ich habe 2 Notizen zu Analysis gefunden, unter anderem: Ableitungen, Integrale."
        in _speech(body)
    )


async def test_search_notes_intent_with_no_results(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("search-notes-token-no-results", "fake-api-key")
    monkeypatch.setattr(handlers, "search_notes_sync", lambda base_url, api_key, query: [])

    body = _invoke(
        "SearchNotesIntent",
        access_token="search-notes-token-no-results",
        slots={"SearchQuery": "Quantenphysik"},
    )

    assert "Ich habe keine Notizen zu Quantenphysik gefunden." in _speech(body)


async def test_search_notes_intent_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("search-notes-token-unreachable", "fake-api-key")

    def _raise(base_url: str, api_key: str, query: str) -> list[dict[str, object]]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "search_notes_sync", _raise)

    body = _invoke(
        "SearchNotesIntent",
        access_token="search-notes-token-unreachable",
        slots={"SearchQuery": "Analysis"},
    )

    assert handlers._STUDYLIFE_UNREACHABLE_SPEECH in _speech(body)


# ---------------------------------------------------------------------------
# CreateNoteIntent
# ---------------------------------------------------------------------------


def test_create_note_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("CreateNoteIntent", access_token=None, slots={"NoteContent": "Kauf Milch"})

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_create_note_intent_empty_content_reprompts_without_calling_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("create-note-token-empty-content", "fake-api-key")
    called = False

    def _fail_if_called(base_url: str, api_key: str, title: str, content: str) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(handlers, "create_note_sync", _fail_if_called)

    body = _invoke(
        "CreateNoteIntent",
        access_token="create-note-token-empty-content",
        slots={"NoteContent": ""},
    )

    assert not called
    assert "Was soll ich mir für dich notieren?" in _speech(body)
    assert body["response"]["reprompt"]["outputSpeech"]["ssml"]


async def test_create_note_intent_missing_slot_reprompts_without_calling_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("create-note-token-missing-slot", "fake-api-key")
    called = False

    def _fail_if_called(base_url: str, api_key: str, title: str, content: str) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(handlers, "create_note_sync", _fail_if_called)

    body = _invoke("CreateNoteIntent", access_token="create-note-token-missing-slot")

    assert not called
    assert "Was soll ich mir für dich notieren?" in _speech(body)


async def test_create_note_intent_success_passes_content_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("create-note-token", "fake-api-key")
    captured: dict[str, str] = {}

    def fake_create_note_sync(
        base_url: str, api_key: str, title: str, content: str
    ) -> dict[str, object]:
        captured["title"] = title
        captured["content"] = content
        return {"id": 1}

    monkeypatch.setattr(handlers, "create_note_sync", fake_create_note_sync)

    body = _invoke(
        "CreateNoteIntent", access_token="create-note-token", slots={"NoteContent": "Kauf Milch"}
    )

    assert captured["content"] == "Kauf Milch"
    assert "Notiz gespeichert." in _speech(body)


async def test_create_note_intent_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("create-note-token-unreachable", "fake-api-key")

    def _raise(base_url: str, api_key: str, title: str, content: str) -> dict[str, object]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "create_note_sync", _raise)

    body = _invoke(
        "CreateNoteIntent",
        access_token="create-note-token-unreachable",
        slots={"NoteContent": "Kauf Milch"},
    )

    assert handlers._STUDYLIFE_UNREACHABLE_SPEECH in _speech(body)
