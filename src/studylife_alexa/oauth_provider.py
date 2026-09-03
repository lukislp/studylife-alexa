"""Account-linking OAuth wrapper around StudyLife's generic connect flow
(identity-contract-v1 SS2). Alexa is treated as a single, fixed, pre-registered
confidential client - no RFC 7591 dynamic registration, no PKCE, no per-client scoping -
so this stays a plain, from-scratch Authorization Code Grant implementation rather than
pulling in a general-purpose OAuth server framework.

Multi-tenant: every user names their OWN self-hosted StudyLife instance during
/authorize (an extra form step, see _instance_form) instead of this server always
redirecting to one operator-configured instance - see oauth_store.py's module
docstring for how that instance URL travels alongside the API key through every later
stage.

Round trip:
  1. Alexa's Account Linking sends the browser to GET /authorize.
  2. If no instance_url is present yet, renders a small form asking for the user's own
     StudyLife instance URL (_instance_form) - submits back to this same endpoint with
     all the original Alexa params preserved as hidden fields, plus instance_url.
  3. Once an instance_url is present and verified reachable, redirects to THAT
     instance's own /connect/client/studylife-alexa (passkey login + consent happens
     entirely on StudyLife's side).
  4. StudyLife redirects back to GET /oauth/studylife/callback with a single-use
     assertion, which this server exchanges server-to-server for a StudyLife API key
     (client.py's exchange_assertion), against the SAME instance_url stashed in step 2.
  5. This server mints its OWN opaque authorization code, stores it mapped to the
     (encrypted) API key AND the instance URL, and redirects to Alexa's own
     redirect_uri.
  6. Alexa's backend calls POST /token server-to-server to exchange that code (or later,
     a refresh token) for this server's own opaque access/refresh tokens.
  7. Every subsequent skill request carries the access token in
     context.System.user.accessToken - handlers.py resolves it back to the underlying
     (StudyLife API key, instance URL) pair via OAuthStore.load_access_token.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import html
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.datastructures import FormData

from studylife_alexa.client import CLIENT_ID, exchange_assertion
from studylife_alexa.config import Settings
from studylife_alexa.metrics import track_upstream
from studylife_alexa.oauth_store import ACCESS_TOKEN_TTL_SECONDS, OAuthStore

# Same single upstream every other outbound call in this service talks to - see
# metrics.py's own docstring for why it's still a label, not baked into the metric name.
_UPSTREAM_TARGET = "studylife-api"

# Mirrors StudyLife's own design system (studylife/src/StudyLife.Client/wwwroot/css/
# base.css) - same font, color tokens, and dark/light handling, so this account-linking
# page doesn't look like a different product from the one it's connecting to.
#
# The 16px input font-size is deliberate, not copied from base.css's own smaller
# 0.875rem .input class: iOS Safari auto-zooms on focusing any input whose *computed*
# font-size is under 16px, regardless of the (also required) viewport meta tag below -
# both are needed together to stop the unwanted zoom-on-tap on a phone.
_BASE_STYLE = """
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;1,9..40,400&display=swap"
  rel="stylesheet">
<style>
  :root {
    color-scheme: dark light;
    --font: 'DM Sans', sans-serif;
    --bg: #0e0e0f; --bg2: #161618; --bg3: #1e1e21;
    --border: rgba(255,255,255,0.07); --border2: rgba(255,255,255,0.12);
    --text: #e8e6e0; --text2: #9d9b93;
    --accent: #CC785C; --radius: 12px;
  }
  @media (prefers-color-scheme: light) {
    :root {
      color-scheme: light;
      --bg: #f4f2ee; --bg2: #ffffff; --bg3: #ebe8e2;
      --border: rgba(0,0,0,0.06); --border2: rgba(0,0,0,0.12);
      --text: #1a1916; --text2: #5a5752; --accent: #CC785C;
    }
  }
  * { box-sizing: border-box; }
  body {
    font-family: var(--font); background: var(--bg); color: var(--text);
    margin: 0; padding: 3rem 1rem; -webkit-font-smoothing: antialiased;
  }
  .card {
    max-width: 26rem; margin: 0 auto; background: var(--bg2);
    border: 1px solid var(--border); border-radius: var(--radius); padding: 2rem;
  }
  .logo { display: block; width: 48px; height: 48px; margin: 0 auto 1.25rem; border-radius: 10px; }
  h1 { font-size: 1.25rem; font-weight: 500; text-align: center; margin: 0 0 0.5rem; }
  p {
    font-size: 0.9rem; color: var(--text2); text-align: center;
    margin: 0 0 1.5rem; line-height: 1.5;
  }
  .error { color: #E17055; }
  input[type="url"] {
    display: block; width: 100%; background: var(--bg3); border: 1px solid var(--border);
    border-radius: 8px; padding: 0.75rem 0.875rem; font-family: var(--font); font-size: 16px;
    color: var(--text); outline: none;
  }
  input[type="url"]:focus { border-color: var(--accent); }
  button {
    display: block; width: 100%; margin-top: 1rem; background: var(--accent); color: #fff;
    border: none; border-radius: 8px; padding: 0.75rem 1.25rem; font-family: var(--font);
    font-size: 0.95rem; font-weight: 500; cursor: pointer;
  }
  button:hover { opacity: 0.9; }
</style>
"""

# Plain __TOKEN__ markers + str.replace() below, not str.format() - the CSS above is
# full of literal { } pairs that .format() would otherwise try (and fail) to parse as
# placeholders.
_ERROR_PAGE = (
    """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>StudyLife</title>"""
    + _BASE_STYLE
    + """</head>
<body>
<div class="card">
<img class="logo" src="/static/icon.png" alt="">
<p>__MESSAGE__</p>
</div>
</body>
</html>
"""
)

_INSTANCE_FORM_PAGE = (
    """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Connect StudyLife</title>"""
    + _BASE_STYLE
    + """</head>
<body>
<div class="card">
<img class="logo" src="/static/icon.png" alt="">
<h1>Connect your StudyLife instance</h1>
<p>Enter the address of your own, self-hosted StudyLife instance.</p>
__ERROR__
<form method="get" action="/authorize">
__HIDDEN_FIELDS__
<input type="url" name="instance_url" placeholder="https://studylife.example.com"
  value="__PREFILL__" required>
<button type="submit">Continue</button>
</form>
</div>
</body>
</html>
"""
)


def _error_page(message: str, *, status_code: int) -> HTMLResponse:
    # message is always a static literal from this module's own call sites (never
    # user input) - see the module-level note near those call sites - so no escaping
    # is strictly required here, but it costs nothing and matches _instance_form's
    # own discipline below.
    page = _ERROR_PAGE.replace("__MESSAGE__", html.escape(message))
    return HTMLResponse(page, status_code=status_code)


def _instance_form(params: dict[str, str], *, prefill: str = "", error: str = "") -> HTMLResponse:
    """params/prefill/error all ultimately trace back to query params on a request
    someone else's browser can be redirected to with arbitrary content (Alexa's own
    state, and instance_url itself) - every one of them is HTML-escaped before going
    into the page, or this would be a reflected-XSS hole."""
    hidden_fields = "\n".join(
        f'<input type="hidden" name="{html.escape(name)}" value="{html.escape(value)}">'
        for name, value in params.items()
    )
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    page = (
        _INSTANCE_FORM_PAGE.replace("__HIDDEN_FIELDS__", hidden_fields)
        .replace("__PREFILL__", html.escape(prefill))
        .replace("__ERROR__", error_html)
    )
    return HTMLResponse(page)


async def _verify_instance_reachable(instance_url: str) -> bool:
    """Sanity check before ever redirecting a user's browser there - GET
    /api/system/version is PublicUnlessInvalidSession (StudyLife's own
    SystemController), reachable with no credential, and returns {"version": "..."}
    only from a real StudyLife instance. Catches a typo'd or unreachable URL before it
    turns into a confusing redirect-to-nowhere."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as http, track_upstream(_UPSTREAM_TARGET) as call:
            response = await http.get(f"{instance_url}/api/system/version")
            if response.status_code != 200:
                call.outcome = "http_error"
        return response.status_code == 200 and "version" in response.json()
    except (httpx.HTTPError, ValueError):
        return False


def _extract_client_credentials(request: Request, form: FormData) -> tuple[str, str]:
    """RFC 6749 SS2.3.1 allows either HTTP Basic auth or client_id/client_secret as form
    fields - Alexa's Account Linking config lets you pick which scheme it uses, so both
    are accepted here."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
        except (ValueError, binascii.Error):
            return "", ""
        client_id, _, client_secret = decoded.partition(":")
        return client_id, client_secret

    return str(form.get("client_id", "")), str(form.get("client_secret", ""))


def _allowed_redirect_uris(settings: Settings) -> set[str]:
    return {uri.strip() for uri in (settings.alexa_redirect_uris or "").split(",") if uri.strip()}


def register_oauth_routes(app: FastAPI, store: OAuthStore, settings: Settings) -> None:
    @app.get("/authorize")
    async def authorize(request: Request) -> Response:
        params = request.query_params
        if params.get("response_type") != "code":
            return JSONResponse({"error": "unsupported_response_type"}, status_code=400)
        if not hmac.compare_digest(params.get("client_id", ""), settings.alexa_client_id or ""):
            return JSONResponse({"error": "unauthorized_client"}, status_code=401)
        redirect_uri = params.get("redirect_uri", "")
        # Alexa's Account Linking gives THREE fixed redirect_uri values, one per
        # regional companion app (see config.py's own comment on
        # alexa_redirect_uris) - which one shows up here depends on which region the
        # user is linking from, so this checks membership, not equality against one
        # value.
        if redirect_uri not in _allowed_redirect_uris(settings):
            return JSONResponse(
                {"error": "invalid_request", "error_description": "redirect_uri mismatch"},
                status_code=400,
            )

        # Alexa's own params must survive the extra instance-selection round trip
        # below as hidden form fields - forwarded verbatim, not re-derived, so nothing
        # here needs to know their exact set beyond what it already validated above.
        alexa_params = {
            "response_type": params["response_type"],
            "client_id": params["client_id"],
            "redirect_uri": redirect_uri,
            "state": params.get("state", ""),
        }

        instance_url = params.get("instance_url", "").strip().rstrip("/")
        if not instance_url:
            return _instance_form(alexa_params)
        if not instance_url.startswith("https://"):
            return _instance_form(
                alexa_params,
                prefill=instance_url,
                error="The instance URL must start with https://.",
            )
        if not await _verify_instance_reachable(instance_url):
            return _instance_form(
                alexa_params,
                prefill=instance_url,
                error=f"Could not reach a StudyLife instance at {instance_url}. "
                "Check the address and try again.",
            )

        # request_id doubles as the state StudyLife's connect flow echoes back on
        # /oauth/studylife/callback - Alexa's own state is stashed alongside it rather
        # than round-tripped through StudyLife directly, so it can't be tampered with by
        # anything in between.
        request_id = secrets.token_urlsafe(24)
        await store.save_pending_authorization(
            request_id,
            alexa_state=alexa_params["state"],
            alexa_redirect_uri=redirect_uri,
            studylife_instance_url=instance_url,
        )

        callback_url = f"{str(settings.alexa_public_url).rstrip('/')}/oauth/studylife/callback"
        query = urlencode({"redirect_uri": callback_url, "state": request_id})
        connect_url = f"{instance_url}/connect/client/{CLIENT_ID}?{query}"
        return RedirectResponse(connect_url, status_code=302)

    @app.get("/oauth/studylife/callback")
    async def studylife_callback(request: Request) -> Response:
        state = request.query_params.get("state", "")
        assertion = request.query_params.get("assertion", "")

        pending = await store.consume_pending_authorization(state)
        if pending is None:
            return _error_page(
                "This connection link is invalid or has expired. "
                "Please restart the connection from the Alexa app.",
                status_code=400,
            )
        if not assertion:
            return _error_page(
                "StudyLife could not confirm this connection - it may have been denied.",
                status_code=400,
            )

        exchanged = await exchange_assertion(pending.studylife_instance_url, assertion)
        if exchanged is None:
            return _error_page(
                "StudyLife could not confirm this connection. Please try again.",
                status_code=401,
            )

        code = secrets.token_urlsafe(32)
        await store.save_authorization_code(code, exchanged.api_key, pending.studylife_instance_url)

        redirect_url = (
            f"{pending.alexa_redirect_uri}?"
            f"{urlencode({'code': code, 'state': pending.alexa_state})}"
        )
        return RedirectResponse(redirect_url, status_code=302)

    @app.post("/token")
    async def token(request: Request) -> Response:
        form = await request.form()
        client_id, client_secret = _extract_client_credentials(request, form)
        if not (
            hmac.compare_digest(client_id, settings.alexa_client_id or "")
            and hmac.compare_digest(client_secret, settings.alexa_client_secret or "")
        ):
            return JSONResponse({"error": "invalid_client"}, status_code=401)

        grant_type = form.get("grant_type")
        if grant_type == "authorization_code":
            linked = await store.consume_authorization_code(str(form.get("code", "")))
        elif grant_type == "refresh_token":
            linked = await store.consume_refresh_token(str(form.get("refresh_token", "")))
        else:
            return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

        if linked is None:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)

        access_token = secrets.token_urlsafe(32)
        refresh_token = secrets.token_urlsafe(32)
        await store.save_access_token(access_token, linked.api_key, linked.base_url)
        await store.save_refresh_token(refresh_token, linked.api_key, linked.base_url)

        return JSONResponse(
            {
                "access_token": access_token,
                "token_type": "Bearer",
                "expires_in": ACCESS_TOKEN_TTL_SECONDS,
                "refresh_token": refresh_token,
            }
        )
