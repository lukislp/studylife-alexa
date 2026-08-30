"""Request handlers for the StudyLife Alexa skill.

TestIntentHandler is Phase-A scaffolding (canned response, proved out the endpoint/
signature-verification/deployment pipeline before any real functionality existed) -
kept around as a no-account-needed connectivity check. Every other intent below (besides
the built-ins) is a real StudyLife-backed call, sharing the same
account-linking-resolution/error-handling shape via _resolve_api_key/_link_account_response.
"""

from __future__ import annotations

from datetime import datetime, timedelta

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
    get_study_program_sync,
    get_timer_state_sync,
    list_all_sessions_sync,
    list_course_goals_sync,
    list_courses_sync,
    list_notes_sync,
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


_FOLLOWUP_REPROMPT = "Sonst noch etwas?"


def _answer(handler_input: HandlerInput, speech: str) -> Response:
    """Speaks the answer and keeps the session open for a follow-up question via
    .ask(), instead of closing the mic after every single query (the ask-sdk default
    when should_end_session is never set) - without this, EVERY question beyond the
    first would need "Alexa, öffne study life" said again first."""
    return (
        handler_input.response_builder.speak(f"{speech} {_FOLLOWUP_REPROMPT}")
        .ask(_FOLLOWUP_REPROMPT)
        .response
    )


def _unreachable_response(handler_input: HandlerInput) -> Response:
    return _answer(handler_input, _STUDYLIFE_UNREACHABLE_SPEECH)


def _pluralize(count: int, singular: str, plural: str) -> str:
    """German has no generic plural suffix rule simple enough to derive automatically
    (Kurs/Kurse, Lernziel/Lernziele, Notiz/Notizen, Stunde/Stunden all differ) - every
    call site spells out its own singular/plural form explicitly."""
    return f"{count} {singular if count == 1 else plural}"


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
        return _answer(handler_input, speech)


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
            speech = f"Du hast aktuell {_pluralize(len(courses), 'Kurs', 'Kurse')} in StudyLife."
        return _answer(handler_input, speech)


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
        return _answer(handler_input, speech)


# TimePeriod slot values resolve to plain spoken text, not a canonical id - matched by
# substring rather than depending on entity resolution, same DIY-over-framework style as
# the rest of this codebase. "letzt" must be checked before the bare "woche"/"monat"
# checks, since "letzte woche" also contains "woche" as a substring. Both "week"
# variants are ROLLING windows relative to now (0-6 / 7-13 days ago), not calendar
# weeks (Mon-Sun) - simpler, and consistent with "heute" already meaning "last 24h"
# rather than "since local midnight". "heute" is also the fallback for an
# empty/unrecognized slot.
#
# Each entry: (days to fetch from the API, window_start_days_ago, window_end_days_ago,
# spoken label). fetch_days must cover window_end_days_ago - the API's own "days" filter
# only returns a trailing window from now, so reaching back to e.g. "letzte Woche" (7-13
# days ago) requires fetching 14 days and filtering client-side down to just that slice
# (_filter_sessions_by_window) - otherwise it would include the current week's sessions
# too and double-count against a "diese Woche" query.
_TIME_PERIODS: dict[str, tuple[int, int, int, str]] = {
    "letzten monat": (60, 30, 59, "letzten Monat"),
    "letzter monat": (60, 30, 59, "letzten Monat"),
    "monat": (30, 0, 29, "diesen Monat"),
    "letzte woche": (14, 7, 13, "letzte Woche"),
    "letzten woche": (14, 7, 13, "letzte Woche"),
    "woche": (7, 0, 6, "diese Woche"),
}


def _period_for_time_period(slot_value: str | None) -> tuple[int, int, int, str]:
    text = (slot_value or "").lower()
    for keyword, period in _TIME_PERIODS.items():
        if keyword in text:
            return period
    return 1, 0, 0, "heute"


def _filter_sessions_by_window(
    sessions: list[dict[str, object]], start_days_ago: int, end_days_ago: int
) -> list[dict[str, object]]:
    now = datetime.now()
    window_start = now - timedelta(days=end_days_ago + 1)
    window_end = now - timedelta(days=start_days_ago)

    filtered = []
    for session in sessions:
        start = session.get("startTime")
        if not isinstance(start, str):
            continue
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError:
            continue
        if window_start <= start_dt <= window_end:
            filtered.append(session)
    return filtered


def _format_duration(total_minutes: int) -> str:
    if total_minutes < 60:
        return _pluralize(total_minutes, "Minute", "Minuten")
    hours, minutes = divmod(total_minutes, 60)
    if minutes == 0:
        return _pluralize(hours, "Stunde", "Stunden")
    return (
        f"{_pluralize(hours, 'Stunde', 'Stunden')} und {_pluralize(minutes, 'Minute', 'Minuten')}"
    )


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

        fetch_days, start_days_ago, end_days_ago, label = _period_for_time_period(
            get_slot_value(handler_input, "TimePeriod")
        )
        try:
            sessions = get_session_history_sync(
                str(settings.studylife_base_url), api_key, fetch_days
            )
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        sessions = _filter_sessions_by_window(sessions, start_days_ago, end_days_ago)
        minutes = _sum_session_minutes(sessions)
        if minutes == 0:
            speech = f"Du hast {label} noch nicht gelernt."
        else:
            speech = f"Du hast {label} {_format_duration(minutes)} gelernt."
        return _answer(handler_input, speech)


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
            speech = (
                "In den letzten sieben Tagen hattest du "
                f"{_pluralize(len(sessions), 'Lernsession', 'Lernsessions')}"
            )
            speech += f", zuletzt in: {names}." if names else "."
        return _answer(handler_input, speech)


def _next_upcoming_session(
    sessions: list[dict[str, object]],
) -> tuple[datetime, str | None] | None:
    now = datetime.now()
    upcoming: list[tuple[datetime, str | None]] = []
    for session in sessions:
        start = session.get("startTime")
        if not isinstance(start, str):
            continue
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError:
            continue
        if start_dt > now:
            course_name = session.get("courseName")
            upcoming.append((start_dt, str(course_name) if course_name else None))
    return min(upcoming, key=lambda pair: pair[0]) if upcoming else None


class NextSessionIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("NextSessionIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            # list_all_sessions_sync (/api/sessions), NOT get_session_history_sync
            # (/api/sessions/history) - the history endpoint only ever looks backward
            # from now, so it can never contain a future/scheduled session.
            sessions = list_all_sessions_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        upcoming = _next_upcoming_session(sessions)
        if upcoming is None:
            speech = "Du hast aktuell keine geplante Lernsession in StudyLife."
        else:
            start_dt, course_name = upcoming
            speech = f"Deine nächste Lernsession ist am {start_dt:%d.%m.} um {start_dt:%H:%M} Uhr"
            speech += f" für {course_name}." if course_name else "."
        return _answer(handler_input, speech)


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
            verb = "ist" if open_goals == 1 else "sind"
            speech = (
                f"Du hast {_pluralize(len(goals), 'Lernziel', 'Lernziele')} in StudyLife, "
                f"davon {verb} {open_goals} noch offen."
            )
        return _answer(handler_input, speech)


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
            speech = (
                f"Du hast {_pluralize(len(programs), 'Studiengang', 'Studiengänge')} "
                f"in StudyLife: {names}."
            )
        return _answer(handler_input, speech)


def _find_program_by_name(
    programs: list[dict[str, object]], query: str
) -> dict[str, object] | None:
    query_lower = query.strip().lower()
    for program in programs:
        name = str(program.get("name", "")).lower()
        if query_lower in name or name in query_lower:
            return program
    return None


def _program_progress(
    detail: dict[str, object], courses: list[dict[str, object]], goals: list[dict[str, object]]
) -> tuple[int, int]:
    """(completed_ects, total_ects) - StudyPrograms.Get only ever returns per-group ECTS
    quotas (max creditable, not progress - see StudyProgramDetailDto), so "progress"
    has to be derived here: sum a course's ects whenever it belongs to one of the
    program's groups AND has a CourseGoal with completedAt set (the same "is this
    course actually done" signal CourseGoalsIntent already uses)."""
    quotas = detail.get("groupEctsQuotas")
    if not isinstance(quotas, dict):
        return 0, 0
    total_ects = sum(int(v) for v in quotas.values() if isinstance(v, int | float))

    completed_course_ids = {
        g.get("courseId") for g in goals if g.get("completedAt") and g.get("courseId") is not None
    }
    completed_ects = 0
    for course in courses:
        ects = course.get("ects")
        if (
            course.get("id") in completed_course_ids
            and course.get("group") in quotas
            and isinstance(ects, int | float)
        ):
            completed_ects += int(ects)
    return completed_ects, total_ects


class ProgramProgressIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("ProgramProgressIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        query = get_slot_value(handler_input, "ProgramName") or ""
        if not query.strip():
            speech = "Für welchen Studiengang möchtest du den Fortschritt wissen?"
            return handler_input.response_builder.speak(speech).ask(speech).response

        base_url = str(settings.studylife_base_url)
        try:
            programs = list_study_programs_sync(base_url, api_key)
            program = _find_program_by_name(programs, query)
            if program is None or program.get("id") is None:
                speech = f"Ich konnte keinen Studiengang namens {query} finden."
                return _answer(handler_input, speech)

            detail = get_study_program_sync(base_url, api_key, int(program["id"]))
            courses = list_courses_sync(base_url, api_key)
            goals = list_course_goals_sync(base_url, api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        completed_ects, total_ects = _program_progress(detail, courses, goals)
        program_name = str(detail.get("name", query))
        if total_ects == 0:
            speech = f"Für {program_name} sind aktuell keine ECTS-Quoten hinterlegt."
        else:
            speech = (
                f"Du hast {completed_ects} von {total_ects} ECTS in {program_name} abgeschlossen."
            )
        return _answer(handler_input, speech)


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
            speech = (
                f"Ich habe {_pluralize(len(notes), 'Notiz', 'Notizen')} zu {query} gefunden, "
                f"unter anderem: {titles}."
            )
        return _answer(handler_input, speech)


class NotesOverviewIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("NotesOverviewIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        resolved = _resolve_api_key(handler_input)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            notes = list_notes_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input)

        if not notes:
            speech = "Du hast aktuell keine Notizen in StudyLife."
        else:
            speech = f"Du hast insgesamt {_pluralize(len(notes), 'Notiz', 'Notizen')} in StudyLife."
        return _answer(handler_input, speech)


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
        return _answer(handler_input, speech)


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
        return _answer(handler_input, speech)
