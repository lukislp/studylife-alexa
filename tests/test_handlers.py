import json
from datetime import datetime, timedelta

import pytest
from ask_sdk_model.request_envelope import RequestEnvelope

from conftest import TEST_INSTANCE_URL
from studylife_alexa import handlers
from studylife_alexa.oauth_store import OAuthStore
from studylife_alexa.strings import DeStrings, EnStrings


def _intent_envelope(
    intent_name: str,
    *,
    access_token: str | None,
    slots: dict[str, str] | None = None,
    locale: str = "de-DE",
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
            "locale": locale,
            "intent": intent,
        },
    }


def _invoke(
    intent_name: str,
    *,
    access_token: str | None,
    slots: dict[str, str] | None = None,
    locale: str = "de-DE",
) -> dict:
    from studylife_alexa.main import _skill

    request_envelope = _skill.serializer.deserialize(
        payload=json.dumps(
            _intent_envelope(intent_name, access_token=access_token, slots=slots, locale=locale)
        ),
        obj_type=RequestEnvelope,
    )
    response_envelope = _skill.invoke(request_envelope, context=None)
    return _skill.serializer.serialize(response_envelope)


def _speech(response_body: dict) -> str:
    return response_body["response"]["outputSpeech"]["ssml"]


async def _link_account(access_token: str, api_key: str, base_url: str = TEST_INSTANCE_URL) -> None:
    from studylife_alexa.config import Settings

    settings = Settings()  # type: ignore[call-arg]
    store = OAuthStore(settings.alexa_oauth_db_path, settings.alexa_token_encryption_key or "")
    await store.initialize()
    await store.save_access_token(access_token, api_key, base_url)


def test_courses_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("CoursesIntent", access_token=None)

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_courses_intent_with_linked_account_calls_studylife(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("real-alexa-access-token", "fake-studylife-api-key")

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

    assert DeStrings.UNREACHABLE in _speech(body)


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
        base_url: str, api_key: str, days: int | None = None, only_completed: bool = True
    ) -> list[dict[str, object]]:
        recorded_days.append(days)
        return [{"startTime": start.isoformat(), "endTime": end.isoformat()}]

    monkeypatch.setattr(handlers, "get_session_history_sync", fake_get_session_history_sync)

    body = _invoke(
        "StudyTimeIntent", access_token="study-time-token-today", slots={"TimePeriod": "heute"}
    )

    assert recorded_days == [1]
    assert "Du hast heute 45 Minuten gelernt." in _speech(body)


async def test_study_time_intent_today_includes_in_progress_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: /api/sessions/history's default onlyCompleted=true hides a session
    that's already started but not yet finished (EndTime in the future, IsCompleted
    still false) - reported live via a 7-hour block session (11:00-18:00) queried at
    14:43 that answered "haven't studied today yet" instead of counting the ~4h
    already elapsed. StudyTimeIntent must fetch with only_completed=False and clamp
    the still-running session's end to now, not its full scheduled duration."""
    await _link_account("study-time-token-in-progress", "fake-api-key")
    recorded_only_completed: list[bool] = []

    start = datetime.now() - timedelta(hours=2)
    scheduled_end = datetime.now() + timedelta(hours=3)  # not finished yet

    def fake_get_session_history_sync(
        base_url: str, api_key: str, days: int | None = None, only_completed: bool = True
    ) -> list[dict[str, object]]:
        recorded_only_completed.append(only_completed)
        return [{"startTime": start.isoformat(), "endTime": scheduled_end.isoformat()}]

    monkeypatch.setattr(handlers, "get_session_history_sync", fake_get_session_history_sync)

    body = _invoke(
        "StudyTimeIntent",
        access_token="study-time-token-in-progress",
        slots={"TimePeriod": "heute"},
    )

    assert recorded_only_completed == [False]
    speech = _speech(body)
    # ~2h elapsed so far, not the full 5h scheduled block.
    assert "2 Stunden" in speech
    assert "5 Stunden" not in speech


async def test_study_time_intent_this_week_over_an_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("study-time-token-week", "fake-api-key")
    recorded_days: list[int | None] = []

    first_start = datetime.now() - timedelta(days=2)
    second_start = datetime.now() - timedelta(days=3)

    def fake_get_session_history_sync(
        base_url: str, api_key: str, days: int | None = None, only_completed: bool = True
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
        base_url: str, api_key: str, days: int | None = None, only_completed: bool = True
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
        base_url: str, api_key: str, days: int | None = None, only_completed: bool = True
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

    def _raise(
        base_url: str, api_key: str, days: int | None = None, only_completed: bool = True
    ) -> list[dict[str, object]]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "get_session_history_sync", _raise)

    body = _invoke(
        "StudyTimeIntent",
        access_token="study-time-token-unreachable",
        slots={"TimePeriod": "heute"},
    )

    assert DeStrings.UNREACHABLE in _speech(body)


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
        base_url: str, api_key: str, days: int | None = None, only_completed: bool = True
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

    def _raise(
        base_url: str, api_key: str, days: int | None = None, only_completed: bool = True
    ) -> list[dict[str, object]]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "get_session_history_sync", _raise)

    body = _invoke("RecentSessionsIntent", access_token="recent-sessions-token-unreachable")

    assert DeStrings.UNREACHABLE in _speech(body)


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

    assert DeStrings.UNREACHABLE in _speech(body)


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

    assert DeStrings.UNREACHABLE in _speech(body)


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

    assert DeStrings.UNREACHABLE in _speech(body)


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

    assert DeStrings.UNREACHABLE in _speech(body)


# ---------------------------------------------------------------------------
# NextSessionIntent
# ---------------------------------------------------------------------------


def test_next_session_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("NextSessionIntent", access_token=None)

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_next_session_intent_picks_nearest_future_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression-shaped: the sessions list is neither sorted nor all-future (it comes
    from /api/sessions, unbounded) - the handler must pick the chronologically nearest
    future session, not the first future one in list order and not a past one."""
    await _link_account("next-session-token", "fake-api-key")

    past_start = datetime.now() - timedelta(days=3)
    far_future_start = datetime.now() + timedelta(days=10, hours=2)
    near_future_start = datetime.now() + timedelta(days=2, hours=5, minutes=15)
    another_past_start = datetime.now() - timedelta(hours=1)

    def fake_list_all_sessions_sync(base_url: str, api_key: str) -> list[dict[str, object]]:
        return [
            {
                "startTime": far_future_start.isoformat(),
                "endTime": (far_future_start + timedelta(hours=1)).isoformat(),
                "courseName": "Statistik",
            },
            {
                "startTime": past_start.isoformat(),
                "endTime": (past_start + timedelta(hours=1)).isoformat(),
                "courseName": "AltesFach",
            },
            {
                "startTime": near_future_start.isoformat(),
                "endTime": (near_future_start + timedelta(hours=1)).isoformat(),
                "courseName": "Analysis",
            },
            {
                "startTime": another_past_start.isoformat(),
                "endTime": (another_past_start + timedelta(hours=1)).isoformat(),
                "courseName": "NochAelter",
            },
        ]

    monkeypatch.setattr(handlers, "list_all_sessions_sync", fake_list_all_sessions_sync)

    body = _invoke("NextSessionIntent", access_token="next-session-token")

    expected = (
        f"Deine nächste Lernsession ist am {near_future_start:%d.%m.} "
        f"um {near_future_start:%H:%M} Uhr für Analysis."
    )
    assert expected in _speech(body)


async def test_next_session_intent_success_keeps_session_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: a successful answer must keep the session open (a follow-up question
    # shouldn't need "Alexa, öffne study life" said again) - shouldEndSession is only
    # present in the JSON at all once something (like .ask()) actually sets it.
    await _link_account("next-session-token-open", "fake-api-key")
    future_start = datetime.now() + timedelta(days=1)

    monkeypatch.setattr(
        handlers,
        "list_all_sessions_sync",
        lambda base_url, api_key: [
            {
                "startTime": future_start.isoformat(),
                "endTime": (future_start + timedelta(hours=1)).isoformat(),
            }
        ],
    )

    body = _invoke("NextSessionIntent", access_token="next-session-token-open")

    assert body["response"]["shouldEndSession"] is False


async def test_next_session_intent_with_only_past_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("next-session-token-only-past", "fake-api-key")
    past_start = datetime.now() - timedelta(days=1)

    monkeypatch.setattr(
        handlers,
        "list_all_sessions_sync",
        lambda base_url, api_key: [
            {
                "startTime": past_start.isoformat(),
                "endTime": (past_start + timedelta(hours=1)).isoformat(),
            }
        ],
    )

    body = _invoke("NextSessionIntent", access_token="next-session-token-only-past")

    assert "Du hast aktuell keine geplante Lernsession in StudyLife." in _speech(body)


async def test_next_session_intent_with_no_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("next-session-token-empty", "fake-api-key")
    monkeypatch.setattr(handlers, "list_all_sessions_sync", lambda base_url, api_key: [])

    body = _invoke("NextSessionIntent", access_token="next-session-token-empty")

    assert "Du hast aktuell keine geplante Lernsession in StudyLife." in _speech(body)


async def test_next_session_intent_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("next-session-token-unreachable", "fake-api-key")

    def _raise(base_url: str, api_key: str) -> list[dict[str, object]]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "list_all_sessions_sync", _raise)

    body = _invoke("NextSessionIntent", access_token="next-session-token-unreachable")

    assert DeStrings.UNREACHABLE in _speech(body)


# ---------------------------------------------------------------------------
# NotesOverviewIntent
# ---------------------------------------------------------------------------


def test_notes_overview_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("NotesOverviewIntent", access_token=None)

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_notes_overview_intent_with_several_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("notes-overview-token", "fake-api-key")
    monkeypatch.setattr(
        handlers,
        "list_notes_sync",
        lambda base_url, api_key: [{"id": 1}, {"id": 2}, {"id": 3}, {"id": 4}],
    )

    body = _invoke("NotesOverviewIntent", access_token="notes-overview-token")

    assert "Du hast insgesamt 4 Notizen in StudyLife." in _speech(body)


async def test_notes_overview_intent_with_exactly_one_note(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("notes-overview-token-one", "fake-api-key")
    monkeypatch.setattr(handlers, "list_notes_sync", lambda base_url, api_key: [{"id": 1}])

    body = _invoke("NotesOverviewIntent", access_token="notes-overview-token-one")

    assert "Du hast insgesamt 1 Notiz in StudyLife." in _speech(body)


async def test_notes_overview_intent_with_no_notes(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("notes-overview-token-empty", "fake-api-key")
    monkeypatch.setattr(handlers, "list_notes_sync", lambda base_url, api_key: [])

    body = _invoke("NotesOverviewIntent", access_token="notes-overview-token-empty")

    assert "Du hast aktuell keine Notizen in StudyLife." in _speech(body)


async def test_notes_overview_intent_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("notes-overview-token-unreachable", "fake-api-key")

    def _raise(base_url: str, api_key: str) -> list[dict[str, object]]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "list_notes_sync", _raise)

    body = _invoke("NotesOverviewIntent", access_token="notes-overview-token-unreachable")

    assert DeStrings.UNREACHABLE in _speech(body)


# ---------------------------------------------------------------------------
# ProgramProgressIntent
# ---------------------------------------------------------------------------


def test_program_progress_intent_without_linked_account_prompts_to_link() -> None:
    body = _invoke("ProgramProgressIntent", access_token=None, slots={"ProgramName": "Informatik"})

    assert "verknüpft" in _speech(body)
    assert body["response"]["card"]["type"] == "LinkAccount"


async def test_program_progress_intent_empty_program_name_reprompts_without_calling_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("program-progress-token-empty-name", "fake-api-key")
    called = {"programs": False, "detail": False, "courses": False, "goals": False}

    def _fail(name: str):
        def _inner(*args: object, **kwargs: object) -> object:
            called[name] = True
            return [] if name != "detail" else {}

        return _inner

    monkeypatch.setattr(handlers, "list_study_programs_sync", _fail("programs"))
    monkeypatch.setattr(handlers, "get_study_program_sync", _fail("detail"))
    monkeypatch.setattr(handlers, "list_courses_sync", _fail("courses"))
    monkeypatch.setattr(handlers, "list_course_goals_sync", _fail("goals"))

    body = _invoke(
        "ProgramProgressIntent",
        access_token="program-progress-token-empty-name",
        slots={"ProgramName": ""},
    )

    assert not any(called.values())
    assert "Für welchen Studiengang möchtest du den Fortschritt wissen?" in _speech(body)
    assert body["response"]["reprompt"]["outputSpeech"]["ssml"]


async def test_program_progress_intent_missing_slot_reprompts_without_calling_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("program-progress-token-missing-slot", "fake-api-key")
    called = {"programs": False, "detail": False, "courses": False, "goals": False}

    def _fail(name: str):
        def _inner(*args: object, **kwargs: object) -> object:
            called[name] = True
            return [] if name != "detail" else {}

        return _inner

    monkeypatch.setattr(handlers, "list_study_programs_sync", _fail("programs"))
    monkeypatch.setattr(handlers, "get_study_program_sync", _fail("detail"))
    monkeypatch.setattr(handlers, "list_courses_sync", _fail("courses"))
    monkeypatch.setattr(handlers, "list_course_goals_sync", _fail("goals"))

    body = _invoke("ProgramProgressIntent", access_token="program-progress-token-missing-slot")

    assert not any(called.values())
    assert "Für welchen Studiengang möchtest du den Fortschritt wissen?" in _speech(body)


async def test_program_progress_intent_no_matching_program_short_circuits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The handler must give up right after list_study_programs_sync when nothing
    fuzzy-matches - it must not go on to fetch program detail/courses/goals."""
    await _link_account("program-progress-token-no-match", "fake-api-key")
    called = {"detail": False, "courses": False, "goals": False}

    def _fail(name: str):
        def _inner(*args: object, **kwargs: object) -> object:
            called[name] = True
            return {} if name == "detail" else []

        return _inner

    monkeypatch.setattr(
        handlers,
        "list_study_programs_sync",
        lambda base_url, api_key: [{"id": 1, "name": "Informatik"}],
    )
    monkeypatch.setattr(handlers, "get_study_program_sync", _fail("detail"))
    monkeypatch.setattr(handlers, "list_courses_sync", _fail("courses"))
    monkeypatch.setattr(handlers, "list_course_goals_sync", _fail("goals"))

    body = _invoke(
        "ProgramProgressIntent",
        access_token="program-progress-token-no-match",
        slots={"ProgramName": "Philosophie"},
    )

    assert not any(called.values())
    assert "Ich konnte keinen Studiengang namens Philosophie finden." in _speech(body)


async def test_program_progress_intent_fuzzy_matches_minor_asr_typo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: found live - voice recognition transcribed "Applied Artificial
    Intelligence" as "applied artifical intelligence" (one dropped letter), which
    failed the old pure-substring match in both directions."""
    await _link_account("program-progress-token-fuzzy", "fake-api-key")

    monkeypatch.setattr(
        handlers,
        "list_study_programs_sync",
        lambda base_url, api_key: [
            {"id": 7, "name": "Applied Artificial Intelligence"},
        ],
    )
    monkeypatch.setattr(
        handlers,
        "get_study_program_sync",
        lambda base_url, api_key, program_id: {
            "id": 7,
            "name": "Applied Artificial Intelligence",
            "groupEctsQuotas": {"Pflicht": 60},
        },
    )
    monkeypatch.setattr(
        handlers,
        "list_courses_sync",
        lambda base_url, api_key: [{"id": 1, "ects": 10, "group": "Pflicht"}],
    )
    monkeypatch.setattr(
        handlers,
        "list_course_goals_sync",
        lambda base_url, api_key: [{"courseId": 1, "completedAt": "2026-01-01T00:00:00"}],
    )

    body = _invoke(
        "ProgramProgressIntent",
        access_token="program-progress-token-fuzzy",
        slots={"ProgramName": "applied artifical intelligence"},
    )

    assert "10 von 60 ECTS in Applied Artificial Intelligence abgeschlossen" in _speech(body)


async def test_program_progress_intent_built_in_program_uses_metrics_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: found live - the built-in study program (StudyProgramSummaryDto.Id
    == null) matched by name just fine, but StudyPrograms.Get requires an int id
    ([HttpGet("{id:int}")]), so there's no way to fetch its ECTS quotas that way.
    Fixed by reading MetricsSummaryDto.Ects via get_metrics_summary_sync(program=0)
    instead, which resolves the built-in program unconditionally server-side - must
    short-circuit before calling get_study_program_sync (which has no id to call
    with) and must pass program=0 explicitly."""
    await _link_account("program-progress-token-builtin", "fake-api-key")
    detail_called = False
    recorded_program: list[int] = []

    def _fail_detail(base_url: str, api_key: str, program_id: int) -> dict[str, object]:
        nonlocal detail_called
        detail_called = True
        return {}

    def fake_get_metrics_summary_sync(
        base_url: str, api_key: str, program: int = 0
    ) -> dict[str, object]:
        recorded_program.append(program)
        return {"ects": {"earned": 15, "total": 50}}

    monkeypatch.setattr(
        handlers,
        "list_study_programs_sync",
        lambda base_url, api_key: [
            {"id": None, "name": "Applied Artificial Intelligence", "isBuiltIn": True}
        ],
    )
    monkeypatch.setattr(handlers, "get_study_program_sync", _fail_detail)
    monkeypatch.setattr(handlers, "get_metrics_summary_sync", fake_get_metrics_summary_sync)

    body = _invoke(
        "ProgramProgressIntent",
        access_token="program-progress-token-builtin",
        slots={"ProgramName": "applied artificial intelligence"},
    )

    assert not detail_called
    assert recorded_program == [0]
    speech = _speech(body)
    assert "15 von 50 ECTS in Applied Artificial Intelligence abgeschlossen" in speech


async def test_program_progress_intent_success_computes_ects_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("program-progress-token", "fake-api-key")

    monkeypatch.setattr(
        handlers,
        "list_study_programs_sync",
        lambda base_url, api_key: [
            {"id": 42, "name": "Informatik B.Sc."},
            {"id": 7, "name": "Mathematik"},
        ],
    )

    def fake_get_study_program_sync(
        base_url: str, api_key: str, program_id: int
    ) -> dict[str, object]:
        assert program_id == 42
        return {
            "id": 42,
            "name": "Informatik B.Sc.",
            "groupEctsQuotas": {"Pflicht": 60, "Wahlpflicht": 30},
        }

    monkeypatch.setattr(handlers, "get_study_program_sync", fake_get_study_program_sync)
    monkeypatch.setattr(
        handlers,
        "list_courses_sync",
        lambda base_url, api_key: [
            {"id": 1, "ects": 10, "group": "Pflicht"},
            {"id": 2, "ects": 5, "group": "Pflicht"},
            {"id": 3, "ects": 8, "group": "Wahlpflicht"},
            # completed, but its group has no quota entry - must NOT count towards
            # either completed or total ECTS.
            {"id": 4, "ects": 6, "group": "Sonstiges"},
        ],
    )
    monkeypatch.setattr(
        handlers,
        "list_course_goals_sync",
        lambda base_url, api_key: [
            {"courseId": 1, "completedAt": "2026-08-01T10:00:00"},
            {"courseId": 2, "completedAt": None},
            {"courseId": 3, "completedAt": "2026-08-02T10:00:00"},
            {"courseId": 4, "completedAt": "2026-08-03T10:00:00"},
        ],
    )

    body = _invoke(
        "ProgramProgressIntent",
        access_token="program-progress-token",
        slots={"ProgramName": "Informatik"},
    )

    # By hand: total = 60 + 30 = 90. Completed = course 1 (10, Pflicht, done) +
    # course 3 (8, Wahlpflicht, done) = 18. Course 2 isn't done; course 4 is done but
    # its group ("Sonstiges") has no quota entry, so it's excluded from both sides.
    assert "Du hast 18 von 90 ECTS in Informatik B.Sc. abgeschlossen." in _speech(body)


async def test_program_progress_intent_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("program-progress-token-unreachable", "fake-api-key")

    monkeypatch.setattr(
        handlers,
        "list_study_programs_sync",
        lambda base_url, api_key: [{"id": 42, "name": "Informatik"}],
    )
    monkeypatch.setattr(
        handlers,
        "get_study_program_sync",
        lambda base_url, api_key, program_id: {
            "id": 42,
            "name": "Informatik",
            "groupEctsQuotas": {"Pflicht": 60},
        },
    )

    def _raise(base_url: str, api_key: str) -> list[dict[str, object]]:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "list_courses_sync", _raise)

    body = _invoke(
        "ProgramProgressIntent",
        access_token="program-progress-token-unreachable",
        slots={"ProgramName": "Informatik"},
    )

    assert DeStrings.UNREACHABLE in _speech(body)


# ---------------------------------------------------------------------------
# en-US locale - a representative subset, not a full duplicate of every German
# test above: strings.py's get_strings/EnStrings are exercised directly and
# exhaustively in test_strings.py, so these just confirm the locale actually
# reaches the handlers end-to-end (get_locale/get_strings wiring) and that a
# couple of the trickier parameterized/pluralized cases resolve correctly.
# ---------------------------------------------------------------------------


def _invoke_launch_request(*, locale: str = "de-DE") -> dict:
    from studylife_alexa.main import _skill

    envelope = _intent_envelope("TestIntent", access_token=None, locale=locale)
    envelope["request"] = {
        "type": "LaunchRequest",
        "requestId": "amzn1.echo-api.request.test",
        "timestamp": "2026-08-30T12:00:00Z",
        "locale": locale,
    }
    request_envelope = _skill.serializer.deserialize(
        payload=json.dumps(envelope), obj_type=RequestEnvelope
    )
    response_envelope = _skill.invoke(request_envelope, context=None)
    return _skill.serializer.serialize(response_envelope)


def test_launch_request_en_us_welcome() -> None:
    body = _invoke_launch_request(locale="en-US")

    assert EnStrings.WELCOME in _speech(body)


def test_test_intent_en_us() -> None:
    body = _invoke("TestIntent", access_token=None, locale="en-US")

    assert EnStrings.TEST_OK in _speech(body)


async def test_courses_intent_en_us_plural(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("en-courses-token-plural", "fake-api-key")
    monkeypatch.setattr(
        handlers, "list_courses_sync", lambda base_url, api_key: [{"id": 1}, {"id": 2}]
    )

    body = _invoke("CoursesIntent", access_token="en-courses-token-plural", locale="en-US")

    assert "2 courses" in _speech(body)
    assert EnStrings.FOLLOWUP_REPROMPT in _speech(body)


async def test_courses_intent_en_us_singular_pluralization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("en-courses-token-single", "fake-api-key")
    monkeypatch.setattr(handlers, "list_courses_sync", lambda base_url, api_key: [{"id": 1}])

    body = _invoke("CoursesIntent", access_token="en-courses-token-single", locale="en-US")

    assert "1 course in StudyLife." in _speech(body)
    assert "1 courses" not in _speech(body)


async def test_timer_status_intent_en_us_running(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("en-timer-token-running", "fake-api-key")
    monkeypatch.setattr(
        handlers,
        "get_timer_state_sync",
        lambda base_url, api_key: {"isRunning": True, "isBreak": False},
    )

    body = _invoke("TimerStatusIntent", access_token="en-timer-token-running", locale="en-US")

    assert EnStrings.TIMER_RUNNING in _speech(body)


async def test_study_time_intent_en_us_last_week_excludes_this_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _link_account("en-study-time-token-last-week", "fake-api-key")

    this_week_start = datetime.now() - timedelta(days=2)
    this_week_end = this_week_start + timedelta(hours=1)
    last_week_start = datetime.now() - timedelta(days=10)
    last_week_end = last_week_start + timedelta(hours=2)

    def fake_get_session_history_sync(
        base_url: str, api_key: str, days: int | None = None, only_completed: bool = True
    ) -> list[dict[str, object]]:
        return [
            {"startTime": this_week_start.isoformat(), "endTime": this_week_end.isoformat()},
            {"startTime": last_week_start.isoformat(), "endTime": last_week_end.isoformat()},
        ]

    monkeypatch.setattr(handlers, "get_session_history_sync", fake_get_session_history_sync)

    body = _invoke(
        "StudyTimeIntent",
        access_token="en-study-time-token-last-week",
        slots={"TimePeriod": "last week"},
        locale="en-US",
    )

    assert "You've studied 2 hours last week." in _speech(body)


async def test_course_goals_intent_en_us_open_goals(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("en-goals-token", "fake-api-key")
    monkeypatch.setattr(
        handlers,
        "list_course_goals_sync",
        lambda base_url, api_key: [
            {"id": 1, "completedAt": None},
            {"id": 2, "completedAt": "2026-01-01T00:00:00"},
        ],
    )

    body = _invoke("CourseGoalsIntent", access_token="en-goals-token", locale="en-US")

    assert "2 study goals" in _speech(body)
    assert "1 of which is still open" in _speech(body)


async def test_program_progress_intent_en_us_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    await _link_account("en-program-not-found-token", "fake-api-key")
    monkeypatch.setattr(
        handlers,
        "list_study_programs_sync",
        lambda base_url, api_key: [{"id": 1, "name": "Physics"}],
    )

    body = _invoke(
        "ProgramProgressIntent",
        access_token="en-program-not-found-token",
        slots={"ProgramName": "Chemistry"},
        locale="en-US",
    )

    assert EnStrings.program_not_found("Chemistry") in _speech(body)


def test_help_intent_en_us() -> None:
    body = _invoke("AMAZON.HelpIntent", access_token=None, locale="en-US")

    assert EnStrings.HELP in _speech(body)


def test_cancel_intent_en_us_goodbye() -> None:
    body = _invoke("AMAZON.CancelIntent", access_token=None, locale="en-US")

    assert EnStrings.GOODBYE in _speech(body)
    assert body["response"]["shouldEndSession"] is True


async def test_timer_status_intent_en_us_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    from studylife_alexa.client import StudyLifeApiError

    await _link_account("en-timer-token-unreachable", "fake-api-key")

    def _raise(base_url: str, api_key: str) -> dict:
        raise StudyLifeApiError(503, "down")

    monkeypatch.setattr(handlers, "get_timer_state_sync", _raise)

    body = _invoke("TimerStatusIntent", access_token="en-timer-token-unreachable", locale="en-US")

    assert EnStrings.UNREACHABLE in _speech(body)
