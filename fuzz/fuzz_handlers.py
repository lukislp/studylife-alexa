"""Atheris fuzz harness for the pure intent helpers in handlers.py.

Contract under test: the helpers that turn StudyLife API payloads (lists of JSON objects)
into spoken answers - session windows, study-time sums, the next upcoming session, program
lookup by spoken name and program progress - never raise for any JSON-shaped input. They
already tolerate missing and mistyped fields; this checks the shapes nobody wrote a test for.

Run locally (Linux, needs the atheris wheel):
    uv sync --frozen --group fuzz
    uv run python fuzz/fuzz_handlers.py -max_total_time=60
CI runs the same harness for a short, fixed time budget (see .github/workflows/ci.yml).
"""

from __future__ import annotations

import json
import sys

import atheris

from studylife_alexa.handlers import (
    _filter_sessions_by_window,
    _find_program_by_name,
    _next_upcoming_session,
    _program_progress,
    _sum_session_minutes,
)


def _json_objects(fdp: atheris.FuzzedDataProvider) -> list[dict[str, object]]:
    try:
        parsed = json.loads(fdp.ConsumeUnicodeNoSurrogates(512))
    except ValueError:
        return []
    if isinstance(parsed, dict):
        return [parsed]
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _timestamp(fdp: atheris.FuzzedDataProvider) -> str:
    """An ISO-8601-looking timestamp with fuzzed fields - random JSON almost never contains
    one, and the date arithmetic in the helpers is exactly what needs exercising: naive and
    offset-aware values, impossible dates, leap days, and the far past/future."""
    stamp = (
        f"{fdp.ConsumeIntInRange(1, 9999):04d}-{fdp.ConsumeIntInRange(0, 13):02d}-"
        f"{fdp.ConsumeIntInRange(0, 32):02d}T{fdp.ConsumeIntInRange(0, 24):02d}:"
        f"{fdp.ConsumeIntInRange(0, 60):02d}:{fdp.ConsumeIntInRange(0, 60):02d}"
    )
    suffix = fdp.ConsumeIntInRange(0, 3)
    if suffix == 1:
        stamp += "Z"
    elif suffix == 2:
        stamp += f"+{fdp.ConsumeIntInRange(0, 14):02d}:00"
    elif suffix == 3:
        stamp += f".{fdp.ConsumeIntInRange(0, 999999):06d}"
    return stamp


def _sessions(fdp: atheris.FuzzedDataProvider) -> list[dict[str, object]]:
    sessions = _json_objects(fdp)
    for _ in range(fdp.ConsumeIntInRange(0, 4)):
        sessions.append(
            {
                "startTime": _timestamp(fdp),
                "endTime": _timestamp(fdp) if fdp.ConsumeBool() else fdp.ConsumeInt(4),
                "courseName": fdp.ConsumeUnicodeNoSurrogates(16) if fdp.ConsumeBool() else None,
            }
        )
    return sessions


def test_one_input(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    sessions = _sessions(fdp)
    start_days_ago = fdp.ConsumeIntInRange(0, 400)
    end_days_ago = fdp.ConsumeIntInRange(0, 400)
    _filter_sessions_by_window(sessions, start_days_ago, end_days_ago)
    _sum_session_minutes(sessions)
    _next_upcoming_session(sessions)

    programs = _json_objects(fdp)
    _find_program_by_name(programs, fdp.ConsumeUnicodeNoSurrogates(64))
    detail = programs[0] if programs else {}
    _program_progress(detail, _json_objects(fdp), _json_objects(fdp))


if __name__ == "__main__":
    # instrument_all() instead of instrument_imports(): the package is loaded through uv's
    # editable-install loader, which the import hook does not see (no coverage feedback,
    # so libFuzzer would never grow its inputs past a few bytes).
    atheris.instrument_all()
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()
