from contextlib import asynccontextmanager

from ask_sdk_runtime.exceptions import AskSdkException
from ask_sdk_webservice_support.webservice_handler import WebserviceSkillHandler
from cryptography.fernet import Fernet
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from studylife_alexa.config import Settings
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

_skill = build_skill(_settings)
_webservice_handler = WebserviceSkillHandler(
    skill=_skill,
    verify_signature=_settings.alexa_verify_requests,
    verify_timestamp=_settings.alexa_verify_requests,
)

register_oauth_routes(app, _store, _settings)


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
