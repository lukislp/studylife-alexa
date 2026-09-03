"""Prometheus metrics for this service (part of the StudyLife telemetry rollout that
already covers studylife-mcp/studylife-ai - same instrument shapes, renamed with this
service's own prefix). Scraped by the existing self-hosted Prometheus (homelab-infra
repo, monitoring/01-prometheus.yaml).

Five instruments:
- HTTP-level rate/latency/status for every route on this app (main.py's middleware).
- Outbound-call rate/latency to StudyLife, by outcome (client.py, oauth_provider.py) -
  this service only ever talks to one upstream, so `target` is always
  "studylife-api" today, but the label is kept for consistency with the sibling repos
  and in case that ever changes.
- Alexa intent volume, by intent/request name and outcome (skill.py's global
  interceptors + handlers.py's CatchAllExceptionHandler, via intent_tracking.py).

Uses the default registry (prometheus_client's module-level collectors), not a custom
CollectorRegistry - process/platform collectors (memory, GC, uptime) come for free from
it, same as studylife-mcp/studylife-ai.
"""

from __future__ import annotations

import time
from types import TracebackType

import httpx
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUEST_DURATION_SECONDS = Histogram(
    "studylife_alexa_request_duration_seconds",
    "HTTP request duration in seconds, by route and method.",
    ["route", "method"],
)

REQUESTS_TOTAL = Counter(
    "studylife_alexa_requests_total",
    "Total HTTP requests, by route, method, and status class.",
    ["route", "method", "status_class"],
)

# target is always "studylife-api" today - every outbound call this service makes goes
# to whatever StudyLife instance the caller linked their account against. Kept as a
# label (rather than hardcoded into the metric name) for consistency with
# studylife-mcp/studylife-ai's own upstream metrics.
UPSTREAM_REQUESTS_TOTAL = Counter(
    "studylife_alexa_upstream_requests_total",
    "Total outbound requests to StudyLife, by target and outcome.",
    ["target", "outcome"],
)

UPSTREAM_REQUEST_DURATION_SECONDS = Histogram(
    "studylife_alexa_upstream_request_duration_seconds",
    "Outbound request duration in seconds, by target.",
    ["target"],
)

INTENTS_TOTAL = Counter(
    "studylife_alexa_intents_total",
    "Total Alexa intent/request invocations, by intent and outcome.",
    ["intent", "outcome"],
)


def render_latest() -> tuple[bytes, str]:
    """Returns (body, content_type) for the /metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST


class UpstreamCall:
    """Context manager recording UPSTREAM_REQUESTS_TOTAL/UPSTREAM_REQUEST_DURATION_SECONDS
    for one outbound call - used at every httpx call site in client.py/oauth_provider.py
    via track_upstream() below. Supports both `with` and `async with` (the bookkeeping
    itself is synchronous either way; only the wrapped httpx call is a real await).

    Usage::

        with track_upstream("studylife-api") as call:
            response = httpx.get(...)
            if response.status_code >= 400:
                call.outcome = "http_error"

    Defaults to outcome="ok" - overridden to "http_error" by the caller (as above) once
    a response with a non-2xx status actually comes back, or automatically to "timeout"/
    "failed" if the call itself raises (httpx.TimeoutException - checked first, since
    it's a subclass of httpx.HTTPError - or any other httpx.HTTPError, respectively). A
    raised exception is never swallowed: __exit__/__aexit__ always return False, so the
    caller's own try/except (if any) still runs exactly as before this wrapping existed.
    """

    def __init__(self, target: str) -> None:
        self.target = target
        self.outcome = "ok"
        self._start = 0.0

    def __enter__(self) -> UpstreamCall:
        self._start = time.perf_counter()
        return self

    async def __aenter__(self) -> UpstreamCall:
        return self.__enter__()

    def _finish(self, exc: BaseException | None) -> None:
        if isinstance(exc, httpx.TimeoutException):
            self.outcome = "timeout"
        elif isinstance(exc, httpx.HTTPError):
            self.outcome = "failed"
        duration = time.perf_counter() - self._start
        UPSTREAM_REQUEST_DURATION_SECONDS.labels(target=self.target).observe(duration)
        UPSTREAM_REQUESTS_TOTAL.labels(target=self.target, outcome=self.outcome).inc()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        self._finish(exc)
        return False

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        self._finish(exc)
        return False


def track_upstream(target: str) -> UpstreamCall:
    return UpstreamCall(target)
