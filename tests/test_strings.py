"""Exhaustive coverage of strings.py's locale lookup and per-locale formatting -
handlers.py's own end-to-end tests (test_handlers.py) only exercise a representative
subset of English strings, relying on this module for full coverage of every
DeStrings/EnStrings method plus the get_strings/period_for_time_period lookup logic.
"""

from __future__ import annotations

from studylife_alexa.strings import DeStrings, EnStrings, get_strings, period_for_time_period


def test_get_strings_returns_german_for_de_de() -> None:
    assert get_strings("de-DE") is DeStrings


def test_get_strings_returns_english_for_en_us() -> None:
    assert get_strings("en-US") is EnStrings


def test_get_strings_falls_back_to_german_for_unknown_locale() -> None:
    assert get_strings("fr-FR") is DeStrings


def test_get_strings_falls_back_to_german_for_none() -> None:
    assert get_strings(None) is DeStrings


def test_period_for_time_period_de_today_default() -> None:
    assert period_for_time_period(DeStrings, None) == (1, 0, 0, "heute")
    assert period_for_time_period(DeStrings, "heute") == (1, 0, 0, "heute")


def test_period_for_time_period_de_last_week_not_confused_with_this_week() -> None:
    # Regression: "letzte woche" must resolve to the lastWeek window, not fall through
    # to the "woche" (this-week) keyword just because it's a substring of the phrase.
    assert period_for_time_period(DeStrings, "letzte woche") == (14, 7, 13, "letzte Woche")
    assert period_for_time_period(DeStrings, "diese woche") == (7, 0, 6, "diese Woche")


def test_period_for_time_period_de_last_month() -> None:
    assert period_for_time_period(DeStrings, "letzten monat") == (60, 30, 59, "letzten Monat")
    assert period_for_time_period(DeStrings, "diesen monat") == (30, 0, 29, "diesen Monat")


def test_period_for_time_period_en_today_default() -> None:
    assert period_for_time_period(EnStrings, None) == (1, 0, 0, "today")
    assert period_for_time_period(EnStrings, "today") == (1, 0, 0, "today")


def test_period_for_time_period_en_last_week_not_confused_with_this_week() -> None:
    assert period_for_time_period(EnStrings, "last week") == (14, 7, 13, "last week")
    assert period_for_time_period(EnStrings, "this week") == (7, 0, 6, "this week")


def test_period_for_time_period_en_last_month() -> None:
    assert period_for_time_period(EnStrings, "last month") == (60, 30, 59, "last month")
    assert period_for_time_period(EnStrings, "this month") == (30, 0, 29, "this month")


def test_de_pluralize_singular_and_plural() -> None:
    assert DeStrings.pluralize(1, "Kurs", "Kurse") == "1 Kurs"
    assert DeStrings.pluralize(2, "Kurs", "Kurse") == "2 Kurse"
    assert DeStrings.pluralize(0, "Kurs", "Kurse") == "0 Kurse"


def test_en_pluralize_singular_and_plural() -> None:
    assert EnStrings.pluralize(1, "course", "courses") == "1 course"
    assert EnStrings.pluralize(2, "course", "courses") == "2 courses"
    assert EnStrings.pluralize(0, "course", "courses") == "0 courses"


def test_de_format_duration_minutes_only() -> None:
    assert DeStrings.format_duration(45) == "45 Minuten"
    assert DeStrings.format_duration(1) == "1 Minute"


def test_de_format_duration_hours_only() -> None:
    assert DeStrings.format_duration(60) == "1 Stunde"
    assert DeStrings.format_duration(120) == "2 Stunden"


def test_de_format_duration_hours_and_minutes() -> None:
    assert DeStrings.format_duration(90) == "1 Stunde und 30 Minuten"


def test_en_format_duration_minutes_only() -> None:
    assert EnStrings.format_duration(45) == "45 minutes"
    assert EnStrings.format_duration(1) == "1 minute"


def test_en_format_duration_hours_only() -> None:
    assert EnStrings.format_duration(60) == "1 hour"
    assert EnStrings.format_duration(120) == "2 hours"


def test_en_format_duration_hours_and_minutes() -> None:
    assert EnStrings.format_duration(90) == "1 hour and 30 minutes"


def test_de_courses_count() -> None:
    assert DeStrings.courses_count(1) == "Du hast aktuell 1 Kurs in StudyLife."
    assert DeStrings.courses_count(3) == "Du hast aktuell 3 Kurse in StudyLife."


def test_en_courses_count() -> None:
    assert EnStrings.courses_count(1) == "You currently have 1 course in StudyLife."
    assert EnStrings.courses_count(3) == "You currently have 3 courses in StudyLife."


def test_de_next_session_with_and_without_course_name() -> None:
    assert (
        DeStrings.next_session("31.08.", "14:00", "Analysis")
        == "Deine nächste Lernsession ist am 31.08. um 14:00 Uhr für Analysis."
    )
    assert (
        DeStrings.next_session("31.08.", "14:00", None)
        == "Deine nächste Lernsession ist am 31.08. um 14:00 Uhr."
    )


def test_en_next_session_with_and_without_course_name() -> None:
    assert (
        EnStrings.next_session("Aug 31", "2:00 PM", "Analysis")
        == "Your next study session is on Aug 31 at 2:00 PM for Analysis."
    )
    assert (
        EnStrings.next_session("Aug 31", "2:00 PM", None)
        == "Your next study session is on Aug 31 at 2:00 PM."
    )


def test_de_goals_count_singular_and_plural_verb() -> None:
    assert "davon ist 1 noch offen" in DeStrings.goals_count(2, 1)
    assert "davon sind 2 noch offen" in DeStrings.goals_count(3, 2)


def test_en_goals_count_singular_and_plural_verb() -> None:
    assert "1 of which is still open" in EnStrings.goals_count(2, 1)
    assert "2 of which are still open" in EnStrings.goals_count(3, 2)


def test_de_program_progress_and_zero() -> None:
    assert DeStrings.program_progress(15, 50, "Informatik") == (
        "Du hast 15 von 50 ECTS in Informatik abgeschlossen."
    )
    assert DeStrings.program_progress_zero("Informatik") == (
        "Für Informatik sind aktuell keine ECTS-Quoten hinterlegt."
    )


def test_en_program_progress_and_zero() -> None:
    assert EnStrings.program_progress(15, 50, "Computer Science") == (
        "You've completed 15 of 50 ECTS in Computer Science."
    )
    assert EnStrings.program_progress_zero("Computer Science") == (
        "There are currently no ECTS quotas set up for Computer Science."
    )


def test_de_program_builtin_no_data() -> None:
    assert "eingebauten Studiengang" in DeStrings.program_builtin_no_data("Applied AI")


def test_en_program_builtin_no_data() -> None:
    assert "built-in study program" in EnStrings.program_builtin_no_data("Applied AI")


def test_de_search_notes_found_and_none() -> None:
    assert DeStrings.search_notes_none("Mathe") == "Ich habe keine Notizen zu Mathe gefunden."
    found = DeStrings.search_notes_found(2, "Mathe", "Titel A, Titel B")
    assert "2 Notizen zu Mathe gefunden" in found
    assert "Titel A, Titel B" in found


def test_en_search_notes_found_and_none() -> None:
    assert EnStrings.search_notes_none("math") == "I couldn't find any notes about math."
    found = EnStrings.search_notes_found(2, "math", "Title A, Title B")
    assert "2 notes about math" in found
    assert "Title A, Title B" in found


def test_de_note_title_and_note_saved() -> None:
    assert DeStrings.note_title("31.08.2026") == "Alexa-Notiz vom 31.08.2026"
    assert DeStrings.NOTE_SAVED == "Notiz gespeichert."


def test_en_note_title_and_note_saved() -> None:
    assert EnStrings.note_title("08/31/2026") == "Alexa note from 08/31/2026"
    assert EnStrings.NOTE_SAVED == "Note saved."
