"""All user-facing speech text, split per locale.

Business logic (API calls, ECTS math, session-window filtering, fuzzy program-name
matching) stays in handlers.py and is NOT duplicated per language - only the
locale-independent, hardcoded-string-per-language question, translated once here.
Duplicating whole handler classes per language would double the bug surface for
every future fix (see e.g. the "letzte Woche" window bug and the built-in-program
bug, each fixed exactly once in the shared handler logic) for zero benefit, since
none of that logic differs by language.

get_strings(locale) is the only entry point handlers.py needs - every handler calls
it once at the top of handle() and then reads plain attributes / calls the small
number of parameterized methods below. Unsupported/unrecognized locales fall back to
German (de-DE), the only locale enabled in the skill's distribution besides en-US at
the time this was written - add a new _Strings subclass and a branch in get_strings
to support another one.
"""

from __future__ import annotations

from typing import ClassVar


class _Strings:
    """Base class documents every key; DeStrings/EnStrings below fill them in.
    Plain class attributes for static text, staticmethods for anything that embeds
    a runtime value (a count, a name, a computed duration) - callers never need to
    instantiate this, they just use the class object itself."""

    FOLLOWUP_REPROMPT: str
    WELCOME: str
    TEST_OK: str
    NOT_LINKED: str
    EXPIRED_LINK: str
    UNREACHABLE: str
    COURSES_NONE: str
    TIMER_NOT_RUNNING: str
    TIMER_BREAK: str
    TIMER_RUNNING: str
    RECENT_SESSIONS_NONE: str
    NEXT_SESSION_NONE: str
    GOALS_NONE: str
    PROGRAMS_NONE: str
    PROGRAM_PROGRESS_ASK: str
    SEARCH_NOTES_ASK: str
    NOTES_NONE: str
    CREATE_NOTE_ASK: str
    NOTE_SAVED: str
    HELP: str
    FALLBACK: str
    GOODBYE: str
    ERROR: str

    # (fetch_days, window_start_days_ago, window_end_days_ago, spoken label) keyed by
    # the lowercased spoken TimePeriod slot text - see handlers.py's own
    # _period_for_time_period for the substring-matching/rolling-window reasoning,
    # which is locale-independent; only the keyword strings and labels differ here.
    TIME_PERIODS: ClassVar[dict[str, tuple[int, int, int, str]]]
    TIME_PERIOD_DEFAULT: tuple[int, int, int, str]

    @staticmethod
    def pluralize(count: int, singular: str, plural: str) -> str:
        raise NotImplementedError

    @staticmethod
    def format_duration(total_minutes: int) -> str:
        raise NotImplementedError

    @staticmethod
    def courses_count(count: int) -> str:
        raise NotImplementedError

    @staticmethod
    def study_time_none(label: str) -> str:
        raise NotImplementedError

    @staticmethod
    def study_time(label: str, duration: str) -> str:
        raise NotImplementedError

    @staticmethod
    def recent_sessions(count: int, names: str) -> str:
        raise NotImplementedError

    @staticmethod
    def next_session(date_str: str, time_str: str, course_name: str | None) -> str:
        raise NotImplementedError

    @staticmethod
    def goals_count(count: int, open_goals: int) -> str:
        raise NotImplementedError

    @staticmethod
    def programs_list(count: int, names: str) -> str:
        raise NotImplementedError

    @staticmethod
    def program_not_found(query: str) -> str:
        raise NotImplementedError

    @staticmethod
    def program_builtin_no_data(program_name: str) -> str:
        raise NotImplementedError

    @staticmethod
    def program_progress_zero(program_name: str) -> str:
        raise NotImplementedError

    @staticmethod
    def program_progress(completed_ects: int, total_ects: int, program_name: str) -> str:
        raise NotImplementedError

    @staticmethod
    def search_notes_none(query: str) -> str:
        raise NotImplementedError

    @staticmethod
    def search_notes_found(count: int, query: str, titles: str) -> str:
        raise NotImplementedError

    @staticmethod
    def notes_overview(count: int) -> str:
        raise NotImplementedError

    @staticmethod
    def note_title(now_str: str) -> str:
        raise NotImplementedError


class DeStrings(_Strings):
    FOLLOWUP_REPROMPT = "Sonst noch etwas?"
    WELCOME = "Willkommen bei Study Life. Sag zum Testen einfach: sag hallo."
    TEST_OK = "Verbindung funktioniert. Study Life ist bereit."
    NOT_LINKED = (
        "Dafür muss dein StudyLife-Konto erst verknüpft werden. "
        "Ich habe dir dazu einen Link in der Alexa-App geschickt."
    )
    EXPIRED_LINK = (
        "Deine Verknüpfung ist abgelaufen. Bitte verbinde dein StudyLife-Konto "
        "in der Alexa-App erneut."
    )
    UNREACHABLE = "StudyLife konnte gerade nicht erreicht werden. Versuch es später noch mal."
    COURSES_NONE = "Du hast aktuell keine Kurse in StudyLife angelegt."
    TIMER_NOT_RUNNING = "Gerade läuft kein Fokus-Timer."
    TIMER_BREAK = "Dein Fokus-Timer läuft, du bist gerade in einer Pause."
    TIMER_RUNNING = "Dein Fokus-Timer läuft gerade."
    RECENT_SESSIONS_NONE = "Du hast in den letzten sieben Tagen keine Lernsessions gehabt."
    NEXT_SESSION_NONE = "Du hast aktuell keine geplante Lernsession in StudyLife."
    GOALS_NONE = "Du hast aktuell keine Lernziele in StudyLife angelegt."
    PROGRAMS_NONE = "Du hast aktuell keinen Studiengang in StudyLife angelegt."
    PROGRAM_PROGRESS_ASK = "Für welchen Studiengang möchtest du den Fortschritt wissen?"
    SEARCH_NOTES_ASK = "Wonach genau soll ich in deinen Notizen suchen?"
    NOTES_NONE = "Du hast aktuell keine Notizen in StudyLife."
    CREATE_NOTE_ASK = "Was soll ich mir für dich notieren?"
    NOTE_SAVED = "Notiz gespeichert."
    HELP = (
        "Du kannst mich zum Beispiel fragen: wie viele Kurse habe ich, "
        "läuft mein Fokus-Timer, wie lange habe ich heute gelernt, "
        "was sind meine Lernziele, oder erstelle eine Notiz."
    )
    FALLBACK = "Das habe ich nicht verstanden. Sag zum Beispiel: wie viele Kurse habe ich."
    GOODBYE = "Bis bald."
    ERROR = "Entschuldigung, da ist etwas schiefgelaufen."

    TIME_PERIODS: ClassVar[dict[str, tuple[int, int, int, str]]] = {
        "letzten monat": (60, 30, 59, "letzten Monat"),
        "letzter monat": (60, 30, 59, "letzten Monat"),
        "monat": (30, 0, 29, "diesen Monat"),
        "letzte woche": (14, 7, 13, "letzte Woche"),
        "letzten woche": (14, 7, 13, "letzte Woche"),
        "woche": (7, 0, 6, "diese Woche"),
    }
    TIME_PERIOD_DEFAULT = (1, 0, 0, "heute")

    @staticmethod
    def pluralize(count: int, singular: str, plural: str) -> str:
        return f"{count} {singular if count == 1 else plural}"

    @staticmethod
    def format_duration(total_minutes: int) -> str:
        if total_minutes < 60:
            return DeStrings.pluralize(total_minutes, "Minute", "Minuten")
        hours, minutes = divmod(total_minutes, 60)
        if minutes == 0:
            return DeStrings.pluralize(hours, "Stunde", "Stunden")
        return (
            f"{DeStrings.pluralize(hours, 'Stunde', 'Stunden')} und "
            f"{DeStrings.pluralize(minutes, 'Minute', 'Minuten')}"
        )

    @staticmethod
    def courses_count(count: int) -> str:
        return f"Du hast aktuell {DeStrings.pluralize(count, 'Kurs', 'Kurse')} in StudyLife."

    @staticmethod
    def study_time_none(label: str) -> str:
        return f"Du hast {label} noch nicht gelernt."

    @staticmethod
    def study_time(label: str, duration: str) -> str:
        return f"Du hast {label} {duration} gelernt."

    @staticmethod
    def recent_sessions(count: int, names: str) -> str:
        speech = (
            "In den letzten sieben Tagen hattest du "
            f"{DeStrings.pluralize(count, 'Lernsession', 'Lernsessions')}"
        )
        return speech + (f", zuletzt in: {names}." if names else ".")

    @staticmethod
    def next_session(date_str: str, time_str: str, course_name: str | None) -> str:
        speech = f"Deine nächste Lernsession ist am {date_str} um {time_str} Uhr"
        return speech + (f" für {course_name}." if course_name else ".")

    @staticmethod
    def goals_count(count: int, open_goals: int) -> str:
        verb = "ist" if open_goals == 1 else "sind"
        return (
            f"Du hast {DeStrings.pluralize(count, 'Lernziel', 'Lernziele')} in StudyLife, "
            f"davon {verb} {open_goals} noch offen."
        )

    @staticmethod
    def programs_list(count: int, names: str) -> str:
        return (
            f"Du hast {DeStrings.pluralize(count, 'Studiengang', 'Studiengänge')} "
            f"in StudyLife: {names}."
        )

    @staticmethod
    def program_not_found(query: str) -> str:
        return f"Ich konnte keinen Studiengang namens {query} finden."

    @staticmethod
    def program_builtin_no_data(program_name: str) -> str:
        return (
            f"Für den eingebauten Studiengang {program_name} sind über die "
            "Schnittstelle leider keine Fortschrittsdaten verfügbar."
        )

    @staticmethod
    def program_progress_zero(program_name: str) -> str:
        return f"Für {program_name} sind aktuell keine ECTS-Quoten hinterlegt."

    @staticmethod
    def program_progress(completed_ects: int, total_ects: int, program_name: str) -> str:
        return f"Du hast {completed_ects} von {total_ects} ECTS in {program_name} abgeschlossen."

    @staticmethod
    def search_notes_none(query: str) -> str:
        return f"Ich habe keine Notizen zu {query} gefunden."

    @staticmethod
    def search_notes_found(count: int, query: str, titles: str) -> str:
        return (
            f"Ich habe {DeStrings.pluralize(count, 'Notiz', 'Notizen')} zu {query} gefunden, "
            f"unter anderem: {titles}."
        )

    @staticmethod
    def notes_overview(count: int) -> str:
        return f"Du hast insgesamt {DeStrings.pluralize(count, 'Notiz', 'Notizen')} in StudyLife."

    @staticmethod
    def note_title(now_str: str) -> str:
        return f"Alexa-Notiz vom {now_str}"


class EnStrings(_Strings):
    FOLLOWUP_REPROMPT = "Anything else?"
    WELCOME = "Welcome to Study Life. To test the connection, just say: say hello."
    TEST_OK = "Connection is working. Study Life is ready."
    NOT_LINKED = "You need to link your StudyLife account first. I've sent a link to the Alexa app."
    EXPIRED_LINK = (
        "Your account link has expired. Please link your StudyLife account again in the Alexa app."
    )
    UNREACHABLE = "StudyLife couldn't be reached right now. Please try again later."
    COURSES_NONE = "You don't have any courses set up in StudyLife yet."
    TIMER_NOT_RUNNING = "Your focus timer isn't running right now."
    TIMER_BREAK = "Your focus timer is running, you're currently on a break."
    TIMER_RUNNING = "Your focus timer is running right now."
    RECENT_SESSIONS_NONE = "You haven't had any study sessions in the last seven days."
    NEXT_SESSION_NONE = "You don't have any study session scheduled in StudyLife right now."
    GOALS_NONE = "You don't have any study goals set up in StudyLife yet."
    PROGRAMS_NONE = "You don't have any study program set up in StudyLife yet."
    PROGRAM_PROGRESS_ASK = "Which study program would you like to know your progress in?"
    SEARCH_NOTES_ASK = "What exactly should I search your notes for?"
    NOTES_NONE = "You don't have any notes in StudyLife right now."
    CREATE_NOTE_ASK = "What should I note down for you?"
    NOTE_SAVED = "Note saved."
    HELP = (
        "You can ask me things like: how many courses do I have, "
        "is my focus timer running, how long have I studied today, "
        "what are my study goals, or create a note."
    )
    FALLBACK = "I didn't get that. Try saying: how many courses do I have."
    GOODBYE = "See you soon."
    ERROR = "Sorry, something went wrong."

    TIME_PERIODS: ClassVar[dict[str, tuple[int, int, int, str]]] = {
        "last month": (60, 30, 59, "last month"),
        "this month": (30, 0, 29, "this month"),
        "last week": (14, 7, 13, "last week"),
        "this week": (7, 0, 6, "this week"),
    }
    TIME_PERIOD_DEFAULT = (1, 0, 0, "today")

    @staticmethod
    def pluralize(count: int, singular: str, plural: str) -> str:
        return f"{count} {singular if count == 1 else plural}"

    @staticmethod
    def format_duration(total_minutes: int) -> str:
        if total_minutes < 60:
            return EnStrings.pluralize(total_minutes, "minute", "minutes")
        hours, minutes = divmod(total_minutes, 60)
        if minutes == 0:
            return EnStrings.pluralize(hours, "hour", "hours")
        return (
            f"{EnStrings.pluralize(hours, 'hour', 'hours')} and "
            f"{EnStrings.pluralize(minutes, 'minute', 'minutes')}"
        )

    @staticmethod
    def courses_count(count: int) -> str:
        return f"You currently have {EnStrings.pluralize(count, 'course', 'courses')} in StudyLife."

    @staticmethod
    def study_time_none(label: str) -> str:
        return f"You haven't studied {label} yet."

    @staticmethod
    def study_time(label: str, duration: str) -> str:
        return f"You've studied {duration} {label}."

    @staticmethod
    def recent_sessions(count: int, names: str) -> str:
        speech = (
            "In the last seven days you've had "
            f"{EnStrings.pluralize(count, 'study session', 'study sessions')}"
        )
        return speech + (f", most recently in: {names}." if names else ".")

    @staticmethod
    def next_session(date_str: str, time_str: str, course_name: str | None) -> str:
        speech = f"Your next study session is on {date_str} at {time_str}"
        return speech + (f" for {course_name}." if course_name else ".")

    @staticmethod
    def goals_count(count: int, open_goals: int) -> str:
        verb = "is" if open_goals == 1 else "are"
        return (
            f"You have {EnStrings.pluralize(count, 'study goal', 'study goals')} in StudyLife, "
            f"{open_goals} of which {verb} still open."
        )

    @staticmethod
    def programs_list(count: int, names: str) -> str:
        return (
            f"You have {EnStrings.pluralize(count, 'study program', 'study programs')} "
            f"in StudyLife: {names}."
        )

    @staticmethod
    def program_not_found(query: str) -> str:
        return f"I couldn't find a study program named {query}."

    @staticmethod
    def program_builtin_no_data(program_name: str) -> str:
        return (
            f"Progress data isn't available through the interface for the built-in "
            f"study program {program_name}."
        )

    @staticmethod
    def program_progress_zero(program_name: str) -> str:
        return f"There are currently no ECTS quotas set up for {program_name}."

    @staticmethod
    def program_progress(completed_ects: int, total_ects: int, program_name: str) -> str:
        return f"You've completed {completed_ects} of {total_ects} ECTS in {program_name}."

    @staticmethod
    def search_notes_none(query: str) -> str:
        return f"I couldn't find any notes about {query}."

    @staticmethod
    def search_notes_found(count: int, query: str, titles: str) -> str:
        return (
            f"I found {EnStrings.pluralize(count, 'note', 'notes')} about {query}, "
            f"including: {titles}."
        )

    @staticmethod
    def notes_overview(count: int) -> str:
        return f"You have {EnStrings.pluralize(count, 'note', 'notes')} in total in StudyLife."

    @staticmethod
    def note_title(now_str: str) -> str:
        return f"Alexa note from {now_str}"


_LOCALES: dict[str, type[_Strings]] = {
    "de-DE": DeStrings,
    "en-US": EnStrings,
}
_DEFAULT_LOCALE = "de-DE"


def get_strings(locale: str | None) -> type[_Strings]:
    return _LOCALES.get(locale or "", _LOCALES[_DEFAULT_LOCALE])


def period_for_time_period(
    strings: type[_Strings], slot_value: str | None
) -> tuple[int, int, int, str]:
    text = (slot_value or "").lower()
    for keyword, period in strings.TIME_PERIODS.items():
        if keyword in text:
            return period
    return strings.TIME_PERIOD_DEFAULT
