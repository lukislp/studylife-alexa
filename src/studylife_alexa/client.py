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


def list_courses_sync(base_url: str, api_key: str) -> list[dict[str, object]]:
    """Plain httpx.Client (not AsyncClient) counterpart to StudyLifeClient.list_courses,
    for handlers.py's use - see oauth_store.load_access_token_sync's docstring for why
    the skill-request path has to stay synchronous end to end."""
    response = httpx.get(
        f"{base_url.rstrip('/')}/api/courses",
        headers={"X-Api-Key": api_key},
        timeout=10.0,
    )
    if response.status_code >= 400:
        raise StudyLifeApiError(response.status_code, response.text)
    return list(response.json())
