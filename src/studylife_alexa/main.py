import time
from contextlib import asynccontextmanager
from pathlib import Path

from ask_sdk_runtime.exceptions import AskSdkException
from ask_sdk_webservice_support.webservice_handler import WebserviceSkillHandler
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from studylife_alexa.config import Settings
from studylife_alexa.metrics import REQUEST_DURATION_SECONDS, REQUESTS_TOTAL, render_latest
from studylife_alexa.oauth_provider import register_oauth_routes
from studylife_alexa.oauth_store import OAuthStore
from studylife_alexa.skill import build_skill

_settings = Settings()  # type: ignore[call-arg]

# Falls back to a freshly generated key when unset, rather than requiring it before the
# server can even start - account linking is opt-in functionality (see config.py's own
# comment), so a deployment that hasn't configured it yet shouldn't crash-loop over it.
# The real consequence of NOT setting ALEXA_TOKEN_ENCRYPTION_KEY: every issued token
# becomes unreadable (and every pending authorization silently starts over) across a
# restart, since the fallback key doesn't persist - fine until account linking is
# actually wired up, not fine after.
_encryption_key = _settings.alexa_token_encryption_key or Fernet.generate_key().decode()
_store = OAuthStore(_settings.alexa_oauth_db_path, _encryption_key)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await _store.initialize()
    yield


app = FastAPI(lifespan=_lifespan)


class MetricsMiddleware(BaseHTTPMiddleware):
    """Times every request through this app and records
    studylife_alexa_request_duration_seconds/studylife_alexa_requests_total - covers
    /alexa/skill, /healthz, and every OAuth route uniformly, without touching any of
    their handler code. /metrics itself is covered too, like any other route.

    The route label is the matched route's own path TEMPLATE (`request.scope["route"]
    .path`), not the raw request path - this app has no id-bearing routes today, but
    reading the raw path would still let an arbitrary 404 probe (e.g.
    "/../../etc/passwd") inject unbounded label values into this metric. A request
    that matches no route at all (a real 404) has no "route" in scope - labeled
    "unmatched" instead, a single fixed value regardless of what was actually
    requested.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - start

        route = request.scope.get("route")
        route_label = route.path if route is not None else "unmatched"
        status_class = f"{response.status_code // 100}xx"

        REQUEST_DURATION_SECONDS.labels(route=route_label, method=request.method).observe(duration)
        REQUESTS_TOTAL.labels(
            route=route_label, method=request.method, status_class=status_class
        ).inc()
        return response


app.add_middleware(MetricsMiddleware)

_skill = build_skill(_settings)
_webservice_handler = WebserviceSkillHandler(
    skill=_skill,
    verify_signature=_settings.alexa_verify_requests,
    verify_timestamp=_settings.alexa_verify_requests,
)

register_oauth_routes(app, _store, _settings)

# Just the StudyLife app icon, for the instance-selection form's logo (oauth_provider.py) -
# small enough that mounting a directory (rather than a single dedicated route) isn't
# over-engineering it, and keeps the icon file itself out of the Python source.
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.post("/alexa/skill")
async def alexa_skill(request: Request) -> JSONResponse:
    body = await request.body()
    try:
        # Despite verify_request_and_dispatch's own docstring claiming :rtype: str,
        # the installed ask-sdk-core version returns the already-deserialized dict
        # (DefaultSerializer.serialize's real return type) - JSONResponse serializes
        # it correctly either way.
        response_body = _webservice_handler.verify_request_and_dispatch(
            dict(request.headers), body.decode("utf-8")
        )
    except AskSdkException:
        # Wrong skill ID, bad/missing signature, or a stale timestamp - all three
        # raise a subclass of AskSdkException. Never let this surface as an unhandled
        # 500; a bad request here means someone else's skill (or a replayed/forged
        # request) is calling this endpoint, not an actual server error.
        return JSONResponse(status_code=403, content={"error": "request rejected"})

    return JSONResponse(content=response_body)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.get("/metrics")
async def metrics() -> Response:
    # Unauthenticated, matching studylife-mcp/studylife-ai's own /metrics - the
    # existing self-hosted Prometheus reaches pods directly inside the cluster
    # (NetworkPolicy-scoped, see k8s/04-network-policies.yaml's
    # allow-monitoring-to-studylife-alexa rule), not through any public ingress path.
    body, content_type = render_latest()
    return Response(content=body, media_type=content_type)
