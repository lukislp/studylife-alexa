"""Request handlers for the StudyLife Alexa skill.

TestIntentHandler is Phase-A scaffolding (canned response, proved out the endpoint/
signature-verification/deployment pipeline before any real functionality existed) -
kept around as a no-account-needed connectivity check. Every other intent below (besides
the built-ins) is a real StudyLife-backed call, sharing the same
account-linking-resolution/error-handling shape via _resolve_api_key/_link_account_response.

All user-facing text is looked up per-request from strings.py via get_strings(locale) -
see that module's own docstring for why business logic here stays language-independent
and unduplicated while only the text varies by locale.
"""

from __future__ import annotations

import difflib
from datetime import datetime, timedelta

from ask_sdk_core.dispatch_components import AbstractExceptionHandler, AbstractRequestHandler
from ask_sdk_core.handler_input import HandlerInput
from ask_sdk_core.utils import (
    get_account_linking_access_token,
    get_locale,
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
from studylife_alexa.strings import _Strings, get_strings, period_for_time_period


def _resolve_api_key(
    handler_input: HandlerInput, strings: type[_Strings]
) -> tuple[Settings, str] | Response:
    """Shared account-linking resolution for every StudyLife-backed intent below.
    Returns (settings, api_key) on success, or a ready-to-return Response (a
    LinkAccountCard prompt) the caller should return immediately as-is."""
    alexa_access_token = get_account_linking_access_token(handler_input)
    if alexa_access_token is None:
        return _link_account_response(handler_input, strings.NOT_LINKED)

    settings = Settings()  # type: ignore[call-arg]
    api_key = load_access_token_sync(
        settings.alexa_oauth_db_path,
        settings.alexa_token_encryption_key or "",
        alexa_access_token,
    )
    if api_key is None:
        return _link_account_response(handler_input, strings.EXPIRED_LINK)

    return settings, api_key


def _link_account_response(handler_input: HandlerInput, speech: str) -> Response:
    return (
        handler_input.response_builder.speak(speech)
        .set_card(LinkAccountCard())
        .set_should_end_session(True)
        .response
    )


def _answer(handler_input: HandlerInput, speech: str, strings: type[_Strings]) -> Response:
    """Speaks the answer and keeps the session open for a follow-up question via
    .ask(), instead of closing the mic after every single query (the ask-sdk default
    when should_end_session is never set) - without this, EVERY question beyond the
    first would need "Alexa, öffne study life" said again first."""
    return (
        handler_input.response_builder.speak(f"{speech} {strings.FOLLOWUP_REPROMPT}")
        .ask(strings.FOLLOWUP_REPROMPT)
        .response
    )


def _unreachable_response(handler_input: HandlerInput, strings: type[_Strings]) -> Response:
    return _answer(handler_input, strings.UNREACHABLE, strings)


class LaunchRequestHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_request_type("LaunchRequest")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        speech = strings.WELCOME
        return handler_input.response_builder.speak(speech).ask(speech).response


class TestIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("TestIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        return _answer(handler_input, strings.TEST_OK, strings)


class CoursesIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("CoursesIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            courses = list_courses_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        speech = strings.COURSES_NONE if not courses else strings.courses_count(len(courses))
        return _answer(handler_input, speech, strings)


class TimerStatusIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("TimerStatusIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            state = get_timer_state_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        if not state.get("isRunning"):
            speech = strings.TIMER_NOT_RUNNING
        elif state.get("isBreak"):
            speech = strings.TIMER_BREAK
        else:
            speech = strings.TIMER_RUNNING
        return _answer(handler_input, speech, strings)


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
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        fetch_days, start_days_ago, end_days_ago, label = period_for_time_period(
            strings, get_slot_value(handler_input, "TimePeriod")
        )
        try:
            sessions = get_session_history_sync(
                str(settings.studylife_base_url), api_key, fetch_days
            )
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        sessions = _filter_sessions_by_window(sessions, start_days_ago, end_days_ago)
        minutes = _sum_session_minutes(sessions)
        if minutes == 0:
            speech = strings.study_time_none(label)
        else:
            speech = strings.study_time(label, strings.format_duration(minutes))
        return _answer(handler_input, speech, strings)


class RecentSessionsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("RecentSessionsIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            sessions = get_session_history_sync(str(settings.studylife_base_url), api_key, days=7)
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        if not sessions:
            speech = strings.RECENT_SESSIONS_NONE
        else:
            names = ", ".join(
                str(s.get("courseName", "-")) for s in sessions[:5] if s.get("courseName")
            )
            speech = strings.recent_sessions(len(sessions), names)
        return _answer(handler_input, speech, strings)


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
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            # list_all_sessions_sync (/api/sessions), NOT get_session_history_sync
            # (/api/sessions/history) - the history endpoint only ever looks backward
            # from now, so it can never contain a future/scheduled session.
            sessions = list_all_sessions_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        upcoming = _next_upcoming_session(sessions)
        if upcoming is None:
            speech = strings.NEXT_SESSION_NONE
        else:
            start_dt, course_name = upcoming
            speech = strings.next_session(f"{start_dt:%d.%m.}", f"{start_dt:%H:%M}", course_name)
        return _answer(handler_input, speech, strings)


class CourseGoalsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("CourseGoalsIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            goals = list_course_goals_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        if not goals:
            speech = strings.GOALS_NONE
        else:
            open_goals = sum(1 for g in goals if not g.get("completedAt"))
            speech = strings.goals_count(len(goals), open_goals)
        return _answer(handler_input, speech, strings)


class StudyProgramsIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("StudyProgramsIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            programs = list_study_programs_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        if not programs:
            speech = strings.PROGRAMS_NONE
        else:
            names = ", ".join(str(p.get("name", "-")) for p in programs)
            speech = strings.programs_list(len(programs), names)
        return _answer(handler_input, speech, strings)


def _find_program_by_name(
    programs: list[dict[str, object]], query: str
) -> dict[str, object] | None:
    query_lower = query.strip().lower()
    if not query_lower:
        return None

    names_lower = [str(p.get("name", "")).lower() for p in programs]

    # Exact substring match first - handles a shortened name ("KI" as part of a longer
    # program name) without needing the fuzzy fallback below.
    for program, name_lower in zip(programs, names_lower, strict=True):
        if query_lower in name_lower or name_lower in query_lower:
            return program

    # Fuzzy fallback for small ASR/spelling differences (found live: voice recognition
    # transcribed "Applied Artificial Intelligence" as "applied artifical intelligence" -
    # one dropped letter is enough to fail a pure substring check either direction).
    close_matches = difflib.get_close_matches(query_lower, names_lower, n=1, cutoff=0.75)
    if close_matches:
        return programs[names_lower.index(close_matches[0])]
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
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        query = get_slot_value(handler_input, "ProgramName") or ""
        if not query.strip():
            speech = strings.PROGRAM_PROGRESS_ASK
            return handler_input.response_builder.speak(speech).ask(speech).response

        base_url = str(settings.studylife_base_url)
        try:
            programs = list_study_programs_sync(base_url, api_key)
            program = _find_program_by_name(programs, query)
            if program is None:
                speech = strings.program_not_found(query)
                return _answer(handler_input, speech, strings)
            if program.get("id") is None:
                # The built-in study program (StudyProgramSummaryDto.Id == null, see
                # StudyProgramsController's own comment) has no DB row, so there's no
                # int id to call StudyPrograms.Get with at all (that route is
                # [HttpGet("{id:int}")]) - a real API gap, not a "not found" case, so
                # it gets its own honest message instead of the generic one above.
                program_name = str(program.get("name", query))
                speech = strings.program_builtin_no_data(program_name)
                return _answer(handler_input, speech, strings)

            detail = get_study_program_sync(base_url, api_key, int(program["id"]))
            courses = list_courses_sync(base_url, api_key)
            goals = list_course_goals_sync(base_url, api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        completed_ects, total_ects = _program_progress(detail, courses, goals)
        program_name = str(detail.get("name", query))
        if total_ects == 0:
            speech = strings.program_progress_zero(program_name)
        else:
            speech = strings.program_progress(completed_ects, total_ects, program_name)
        return _answer(handler_input, speech, strings)


class SearchNotesIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("SearchNotesIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        query = get_slot_value(handler_input, "SearchQuery") or ""
        if not query.strip():
            speech = strings.SEARCH_NOTES_ASK
            return handler_input.response_builder.speak(speech).ask(speech).response

        try:
            notes = search_notes_sync(str(settings.studylife_base_url), api_key, query)
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        if not notes:
            speech = strings.search_notes_none(query)
        else:
            titles = ", ".join(str(n.get("title", "-")) for n in notes[:5])
            speech = strings.search_notes_found(len(notes), query, titles)
        return _answer(handler_input, speech, strings)


class NotesOverviewIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("NotesOverviewIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        try:
            notes = list_notes_sync(str(settings.studylife_base_url), api_key)
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        speech = strings.NOTES_NONE if not notes else strings.notes_overview(len(notes))
        return _answer(handler_input, speech, strings)


class CreateNoteIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("CreateNoteIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        resolved = _resolve_api_key(handler_input, strings)
        if isinstance(resolved, Response):
            return resolved
        settings, api_key = resolved

        content = get_slot_value(handler_input, "NoteContent") or ""
        if not content.strip():
            speech = strings.CREATE_NOTE_ASK
            return handler_input.response_builder.speak(speech).ask(speech).response

        title = strings.note_title(f"{datetime.now():%d.%m.%Y}")
        try:
            create_note_sync(str(settings.studylife_base_url), api_key, title, content)
        except StudyLifeApiError:
            return _unreachable_response(handler_input, strings)

        return _answer(handler_input, strings.NOTE_SAVED, strings)


class HelpIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.HelpIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        speech = strings.HELP
        return handler_input.response_builder.speak(speech).ask(speech).response


class FallbackIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.FallbackIntent")(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        speech = strings.FALLBACK
        return handler_input.response_builder.speak(speech).ask(speech).response


class CancelOrStopIntentHandler(AbstractRequestHandler):
    def can_handle(self, handler_input: HandlerInput) -> bool:
        return is_intent_name("AMAZON.CancelIntent")(handler_input) or is_intent_name(
            "AMAZON.StopIntent"
        )(handler_input)

    def handle(self, handler_input: HandlerInput) -> Response:
        strings = get_strings(get_locale(handler_input))
        return (
            handler_input.response_builder.speak(strings.GOODBYE)
            .set_should_end_session(True)
            .response
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
        strings = get_strings(get_locale(handler_input))
        return _answer(handler_input, strings.ERROR, strings)
