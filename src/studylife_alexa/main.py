from ask_sdk_runtime.exceptions import AskSdkException
from ask_sdk_webservice_support.webservice_handler import WebserviceSkillHandler
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from studylife_alexa.config import Settings
from studylife_alexa.skill import build_skill

app = FastAPI()

_settings = Settings()  # type: ignore[call-arg]
_skill = build_skill(_settings)
_webservice_handler = WebserviceSkillHandler(
    skill=_skill,
    verify_signature=_settings.alexa_verify_requests,
    verify_timestamp=_settings.alexa_verify_requests,
)


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
