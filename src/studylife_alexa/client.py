"""Typed HTTP client for StudyLife's REST API and the generic OAuth-client connect flow
(identity-contract-v1 SS2, the same one studylife-cli/studylife-mcp's own client.py use) -
scoped to exactly what this skill needs: the assertion exchange for account linking, and
the read-only calls its intents make on the user's behalf.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

CLIENT_ID = "studylife-alexa"


class StudyLifeApiError(Exception):
    """Raised for any non-2xx response from StudyLife, carrying the status and body."""

    def __init__(self, status_code: int, body: str) -> None:
        super().__init__(f"StudyLife API returned {status_code}: {body.strip()}")
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class ExchangedAssertion:
    user_id: int
    api_key: str


async def exchange_assertion(base_url: str, assertion: str) -> ExchangedAssertion | None:
    """Server-to-server exchange of the single-use assertion authorize()'s callback
    received for the real StudyLife user id and a freshly issued, per-installation API
    key (generic flow - AuthController.10.OAuthClients.cs). No X-Api-Key sent: this
    endpoint is [AllowAnonymous] by design, the assertion itself is the one-time
    credential. Returns None on any failure - the caller renders a generic "connection
    failed" page either way, so the specific reason only matters for logs."""
    async with httpx.AsyncClient(timeout=10.0) as http:
        try:
            response = await http.post(
                f"{base_url.rstrip('/')}/api/auth/assertion-exchange",
                json={"clientId": CLIENT_ID, "assertion": assertion},
            )
        except httpx.HTTPError:
            return None

    if response.status_code != 200:
        return None

    try:
        data = response.json()
        return ExchangedAssertion(user_id=int(data["userId"]), api_key=str(data["apiKey"]))
    except (KeyError, TypeError, ValueError):
        return None


class StudyLifeClient:
    """Talks to StudyLife on behalf of one already-linked user, using their own
    per-installation API key (X-Api-Key) - the same header every other add-on uses."""

    def __init__(self, base_url: str, api_key: str, timeout: float = 10.0) -> None:
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-Api-Key": api_key},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> StudyLifeClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _request(self, method: str, path: str, **kwargs: object) -> httpx.Response:
        response = await self._http.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise StudyLifeApiError(response.status_code, response.text)
        return response

    async def list_courses(self) -> list[dict[str, object]]:
        response = await self._request("GET", "/api/courses")
        return list(response.json())


def _sync_get(
    base_url: str, api_key: str, path: str, params: dict[str, object] | None = None
) -> httpx.Response:
    """Shared plain-httpx GET for every *_sync StudyLife call below - see
    oauth_store.load_access_token_sync's docstring for why the skill-request path has to
    stay synchronous end to end (AsyncClient/StudyLifeClient above is for the FastAPI
    routes, which don't hit this restriction)."""
    response = httpx.get(
        f"{base_url.rstrip('/')}{path}",
        headers={"X-Api-Key": api_key},
        params=params,
        timeout=10.0,
    )
    if response.status_code >= 400:
        raise StudyLifeApiError(response.status_code, response.text)
    return response


def list_courses_sync(base_url: str, api_key: str) -> list[dict[str, object]]:
    return list(_sync_get(base_url, api_key, "/api/courses").json())


def get_timer_state_sync(base_url: str, api_key: str) -> dict[str, object]:
    return dict(_sync_get(base_url, api_key, "/api/timerstate").json())


def get_session_history_sync(
    base_url: str, api_key: str, days: int | None = None
) -> list[dict[str, object]]:
    params: dict[str, object] = {"days": days} if days is not None else {}
    return list(_sync_get(base_url, api_key, "/api/sessions/history", params).json())


def list_course_goals_sync(base_url: str, api_key: str) -> list[dict[str, object]]:
    return list(_sync_get(base_url, api_key, "/api/coursegoals").json())


def list_study_programs_sync(base_url: str, api_key: str) -> list[dict[str, object]]:
    return list(_sync_get(base_url, api_key, "/api/studyprograms").json())


def get_study_program_sync(base_url: str, api_key: str, program_id: int) -> dict[str, object]:
    return dict(_sync_get(base_url, api_key, f"/api/studyprograms/{program_id}").json())


def list_all_sessions_sync(base_url: str, api_key: str) -> list[dict[str, object]]:
    """Unlike get_session_history_sync (/api/sessions/history, a trailing window from
    now), this hits plain /api/sessions - unbounded, includes future/scheduled sessions
    too (SessionsController.GetAll's own comment: "the client fetches this once and does
    all week/day navigation itself" - it's the same endpoint studylife's own calendar
    view uses)."""
    return list(_sync_get(base_url, api_key, "/api/sessions").json())


def list_notes_sync(base_url: str, api_key: str) -> list[dict[str, object]]:
    return list(_sync_get(base_url, api_key, "/api/notes").json())


def search_notes_sync(base_url: str, api_key: str, query: str) -> list[dict[str, object]]:
    return list(_sync_get(base_url, api_key, "/api/notes/search", {"q": query}).json())


def create_note_sync(base_url: str, api_key: str, title: str, content: str) -> dict[str, object]:
    response = httpx.post(
        f"{base_url.rstrip('/')}/api/notes",
        headers={"X-Api-Key": api_key},
        json={"title": title, "content": content},
        timeout=10.0,
    )
    if response.status_code >= 400:
        raise StudyLifeApiError(response.status_code, response.text)
    return dict(response.json())
