"""Request handlers for the StudyLife Alexa skill.

TestIntentHandler is Phase-A scaffolding (canned response, proved out the endpoint/
signature-verification/deployment pipeline before any real functionality existed) -
kept around as a no-account-needed connectivity check. Every other intent below (besides
the built-ins) is a real StudyLife-backed call, sharing the same
account-linking-resolution/error-handling shape via _resolve_api_key/_link_account_response.
"""

from __future__ import annotations

from datetime import datetime

from ask_sdk_core.dispatch_components import AbstractExceptionHandler, AbstractRequestHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import (
    get_account_linking_access_token,
    get_slot_value,
    is_intent_name,
    is_request_type,
)
from ask_sdk_model import Response
from ask_sdk_model.ui import LinkAccountCard

from studylife_alexa.client import (
    StudyLifeApiError,
    create_note_sync,
    get_session_history_sync,
    get_timer_state_sync,
    list_course_goals_sync,
    list_courses_sync,
    list_study_programs_sync,
    search_notes_sync,
)
from studylife_alexa.config import Settings
from studylife_alexa.oauth_store import load_access_token_sync

_NOT_LINKED_SPEECH = (
    "Dafür muss dein StudyLife-Konto erst verknüpft werden. "
    "Ich habe dir dazu einen Link in der Alexa-App geschickt."
)
_EXPIRED_LINK_SPEECH = (
    "Deine Verknüpfung ist abgelaufen. Bitte verbinde dein StudyLife-Konto in der Alexa-App erneut."
)
_STUDYLIFE_UNREACHABLE_SPEECH = (
    "StudyLife konnte gerade nicht erreicht werden. Versuch es später noch mal."
)


def _resolve_api_key(handler_input: HandlerInput) -> tuple[Settings, str] | Response:
    """Shared account-linking resolution for every StudyLife-backed intent below.
    Returns (settings, api_key) on success, or a ready-to-return Response (a
    LinkAccountCard prompt) the caller should return immediately as-is."""
    alexa_access_token = get_account_linking_access_token(handler_input)
    if alexa_access_token is None:
        return _link_account_response(handler_input, _NOT_LINKED_SPEECH)

    settings = Settings()  # type: ignore[call-arg]
    api_key = load_access_token_sync(
        settings.alexa_oauth_db_path,
        settings.alexa_token_encryption_key or "",
        alexa_access_token,
    )
    if api_key is None:
        return _link_account_response(handler_input, _EXPIRED_LINK_SPEECH)

    return settings, api_key


def _link_account_response(handler_input: HandlerInput, speech: str) -> Response:
    return (
        handler_input.response_builder.speak(speech)
        .set_card(LinkAccountCard())
        .set_should_end_session(True)
        .response
    )


def _unreachable_response(handler_input: HandlerInput) -> Response:
    return handler_input.response_builder.speak(_STUDYLIFE_UNREACHABLE_SPEECH).response


class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speech = "Willkommen bei Study Life. Sag zum Testen einfach: sag hallo."
        return handler_input.response_builder.speak(speech).ask(speech).response


class TestIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("TestIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speech = "Verbindung funktioniert. Study Life ist bereit."
        return handler_input.response_builder.speak(speech).response


class CoursesIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("CoursesIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            courses = list_courses_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        if not courses:
            speech = "Du hast aktuell keine Kurse in StudyLife angelegt."
        else:
            speech = f"Du hast aktuell {len(courses)} Kurse in StudyLife."
        return handler_input.response_builder.speak(speech).response


class TimerStatusIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("TimerStatusIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            state = get_timer_state_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        if not state.get("isRunning"):
            speech = "Gerade läuft kein Fokus-Timer."
        elif state.get("isBreak"):
            speech = "Dein Fokus-Timer läuft, du bist gerade in einer Pause."
        else:
            speech = "Dein Fokus-Timer läuft gerade."
        return handler_input.response_builder.speak(speech).response


# TimePeriod slot values (heute/diese woche/diesen monat) resolve to plain spoken text,
# not a canonical id - matched by substring rather than depending on entity resolution,
# same DIY-over-framework style as the rest of this codebase. "heute" is also the
# fallback for an empty/unrecognized slot.
_TIME_PERIOD_DAYS = {"monat": 30, "woche": 7}


def _days_for_time_period(slot_value: str | None) -> tuple[int, str]:
    text = (slot_value or "").lower()
    for keyword, days in _TIME_PERIOD_DAYS.items():
        if keyword in text:
            label = "diesen Monat" if keyword == "monat" else "diese Woche"
            return days, label
    return 1, "heute"


def _format_duration(total_minutes: int) -> str:
    def _unit(count: int, singular: str, plural: str) -> str:
        return f"{count} {singular if count == 1 else plural}"

    if total_minutes < 60:
        return _unit(total_minutes, "Minute", "Minuten")
    hours, minutes = divmod(total_minutes, 60)
    if minutes == 0:
        return _unit(hours, "Stunde", "Stunden")
    return f"{_unit(hours, 'Stunde', 'Stunden')} und {_unit(minutes, 'Minute', 'Minuten')}"


def _sum_session_minutes(sessions: list[dict[str, object]]) -> int:
    total_seconds = 0.0
    for session in sessions:
        start, end = session.get("startTime"), session.get("endTime")
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        try:
            total_seconds += (
                datetime.fromisoformat(end) - datetime.fromisoformat(start)
            ).total_seconds()
        except ValueError:
            continue
    return int(total_seconds // 60)


class StudyTimeIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("StudyTimeIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        days, label = _days_for_time_period(get_slot_value(handler_input, "TimePeriod"))
        try:
            sessions = get_session_history_sync(str(settings.studylife_base_url), api_key, days)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        minutes = _sum_session_minutes(sessions)
        if minutes == 0:
            speech = f"Du hast {label} noch nicht gelernt."
        else:
            speech = f"Du hast {label} {_format_duration(minutes)} gelernt."
        return handler_input.response_builder.speak(speech).response


class RecentSessionsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("RecentSessionsIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            sessions = get_session_history_sync(str(settings.studylife_base_url), api_key, days=7)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        if not sessions:
            speech = "Du hast in den letzten sieben Tagen keine Lernsessions gehabt."
        else:
            names = ", ".join(
                str(s.get("courseName", "-")) for s in sessions[:5] if s.get("courseName")
            )
            speech = f"In den letzten sieben Tagen hattest du {len(sessions)} Lernsessions"
            speech += f", zuletzt in: {names}." if names else "."
        return handler_input.response_builder.speak(speech).response


class CourseGoalsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("CourseGoalsIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            goals = list_course_goals_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        if not goals:
            speech = "Du hast aktuell keine Lernziele in StudyLife angelegt."
        else:
            open_goals = sum(1 for g in goals if not g.get("completedAt"))
            speech = (
                f"Du hast {len(goals)} Lernziele in StudyLife, davon sind {open_goals} noch offen."
            )
        return handler_input.response_builder.speak(speech).response


class StudyProgramsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("StudyProgramsIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            programs = list_study_programs_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        if not programs:
            speech = "Du hast aktuell keinen Studiengang in StudyLife angelegt."
        else:
            names = ", ".join(str(p.get("name", "-")) for p in programs)
            speech = f"Du hast {len(programs)} Studiengänge in StudyLife: {names}."
        return handler_input.response_builder.speak(speech).response


class SearchNotesIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("SearchNotesIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        query = get_slot_value(handler_input, "SearchQuery") or ""
        if not query.strip():
            speech = "Wonach genau soll ich in deinen Notizen suchen?"
            return handler_input.response_builder.speak(speech).ask(speech).response

        try:
            notes = search_notes_sync(str(settings.studylife_base_url), api_key, query)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        if not notes:
            speech = f"Ich habe keine Notizen zu {query} gefunden."
        else:
            titles = ", ".join(str(n.get("title", "-")) for n in notes[:5])
            speech = f"Ich habe {len(notes)} Notizen zu {query} gefunden, unter anderem: {titles}."
        return handler_input.response_builder.speak(speech).response


class CreateNoteIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("CreateNoteIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        content = get_slot_value(handler_input, "NoteContent") or ""
        if not content.strip():
            speech = "Was soll ich mir für dich notieren?"
            return handler_input.response_builder.speak(speech).ask(speech).response

        title = f"Alexa-Notiz vom {datetime.now():%d.%m.%Y}"
        try:
            create_note_sync(str(settings.studylife_base_url), api_key, title, content)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        speech = "Notiz gespeichert."
        return handler_input.response_builder.speak(speech).response


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speech = (
            "Du kannst mich zum Beispiel fragen: wie viele Kurse habe ich, "
            "läuft mein Fokus-Timer, wie lange habe ich heute gelernt, "
            "was sind meine Lernziele, oder erstelle eine Notiz."
        )
        return handler_input.response_builder.speak(speech).ask(speech).response


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        speech = "Das habe ich nicht verstanden. Sag zum Beispiel: wie viele Kurse habe ich."
        return handler_input.response_builder.speak(speech).ask(speech).response


class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.CancelIntent")(handler_input) or is_intent_name(
            "AMAZON.StopIntent"
        )(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        return (
            handler_input.response_builder.speak("Bis bald.").set_should_end_session(True).response
        )


class SessionEndedRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("SessionEndedRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        # Alexa ignores any response body for SessionEndedRequest - nothing to build.
        return handler_input.response_builder.response


class CatchAllExceptionHandler(AbstractExceptionHandler):
    def can_handle(self, handler_input: HandlerInput, exception: Exception) -> bool:
        return True

    def handle(self, handler_input: HandlerInput, exception: Exception) -> Response:
        speech = "Entschuldigung, da ist etwas schiefgelaufen."
        return handler_input.response_builder.speak(speech).response
