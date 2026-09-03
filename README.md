# studylife-alexa

Alexa Skill backend for [StudyLife](https://github.com/lukislp/studylife): voice control for
the focus timer and study sessions, account-linked to your own StudyLife instance.

## Status

- `LaunchRequest` - welcome message
- `TestIntent` - confirms the connection is working, no account needed
- `CoursesIntent` - "wie viele Kurse habe ich"
- `TimerStatusIntent` - "läuft mein Fokus-Timer" (read-only - `TimerState` has no
  publicly-grantable start/stop scope, only `Get`)
- `StudyTimeIntent` - "wie lange habe ich {heute/diese Woche/letzte Woche/diesen
  Monat/letzten Monat} gelernt" (custom `TimePeriod` slot, 5 rolling windows - see
  `period_for_time_period` in `strings.py`)
- `RecentSessionsIntent` - "zeig meine letzten Lernsessions"
- `NextSessionIntent` - "wann ist meine nächste Lernsession" (`/api/sessions`, unlike
  `RecentSessionsIntent`/`StudyTimeIntent` which use `/api/sessions/history` - the only
  endpoint that returns future/scheduled sessions at all)
- `CourseGoalsIntent` - "was sind meine Lernziele"
- `StudyProgramsIntent` - "zeig meine Studiengänge"
- `ProgramProgressIntent` - "wie ist mein Fortschritt im Studiengang {ProgramName}" -
  for a custom program, `StudyPrograms.Get` only returns per-group ECTS quotas, not
  actual progress, so this derives completed ECTS itself from `Courses` + `CourseGoals`
  (see `_program_progress`); for the built-in program (no DB row, no int id to call
  `StudyPrograms.Get` with at all) this instead reads `Metrics.GetSummary`'s
  `Ects.{Earned,Total}` with `program=0`, which resolves the built-in program
  unconditionally server-side
- `SearchNotesIntent` - "suche Notizen zu {SearchQuery}"
- `NotesOverviewIntent` - "wie viele Notizen habe ich insgesamt"
- `CreateNoteIntent` - "erstelle eine Notiz {NoteContent}"
- `AMAZON.HelpIntent` / `AMAZON.FallbackIntent` / `AMAZON.CancelIntent` /
  `AMAZON.StopIntent` - built-ins

Every StudyLife-backed intent shares the same account-linking resolution
(`_resolve_api_key`/`_link_account_response` in `handlers.py`) - falls back to a
`LinkAccountCard` prompt if the account isn't linked yet or the link expired.

Deliberately not exposed via voice: deleting/editing notes, sessions, or course
goals - too easy to target the wrong item without a visual confirmation step. Would
need a real confirmation-dialog design first, not just wiring up the existing
`Delete`/`Update` scopes.

## Languages

Supports `de-DE` (default/fallback for any unrecognized locale) and `en-US`. All
handler logic (API calls, ECTS math, session-window filtering, fuzzy program-name
matching) is shared and language-independent; every user-facing string lives in
`strings.py`'s `DeStrings`/`EnStrings` classes, looked up per-request via
`get_strings(get_locale(handler_input))`. Adding another language means adding one
new `_Strings` subclass and a matching interaction model in the Alexa Developer
Console's locale tab for that language - no handler changes needed. Each locale needs
its own interaction model configured in the console (Build tab -> Add a new locale);
this repo doesn't track the interaction model JSON itself, since it only ever lives in
the console.

## Development

```bash
uv sync
cp .env.example .env   # fill in ALEXA_SKILL_ID from the Alexa Developer Console
uv run uvicorn studylife_alexa.main:app --reload
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Account linking

Any intent that calls StudyLife on the user's behalf (`CoursesIntent` and onward) needs
account linking - a small OAuth 2.0 Authorization Code Grant server
(`oauth_provider.py`) wraps StudyLife's own generic connect flow
(identity-contract-v1 SS2, the same one [studylife-cli](https://github.com/lukislp/studylife-cli)
uses), rather than exposing StudyLife's login to Alexa directly.

**Multi-tenant**: this server is not wired to one fixed StudyLife instance. Every user
names their own self-hosted instance during linking - `/authorize` shows a small form
asking for it (pinging `/api/system/version` first to catch a typo'd/unreachable URL
before ever redirecting there) - and that URL travels alongside their API key through
the whole flow (see `oauth_store.py`'s module docstring). Two different people (or two
accounts on the *same* shared instance - the instance URL is just routing, not
identity) can link independently without stepping on each other.

Setting this server up (once, by whoever deploys it) still needs:

1. Register this skill as an ordinary add-on on **your own**
   [studylife-developers](https://github.com/lukislp/studylife-developers) instance
   (each user who wants to link an account does this on THEIR OWN instance, not the
   deployer's): **Client ID**: `studylife-alexa`, **Allowed redirect URIs**:
   `https://<your-public-url>/oauth/studylife/callback`. Scopes, matching the intents
   in [Status](#status) above: Read the course catalog, Read live timer state, Read
   session history, Read course goals, Read study programs, Read metrics summary,
   Search notes, Create notes.
2. Generate a client ID/secret pair for Alexa itself and a token encryption key:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"  # x2, for ALEXA_CLIENT_ID/SECRET
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
3. In the Alexa Developer Console's **Account Linking** page:
   - Authorization URI: `https://<your-public-url>/authorize`
   - Access Token URI: `https://<your-public-url>/token`
   - Client ID / Secret: the values generated above
   - Client Authentication Scheme: HTTP Basic (or Credentials in request body - both are
     accepted, see `oauth_provider.py`'s `_extract_client_credentials`)
   - Scope: `studylife` (any non-empty value works - this server doesn't currently
     differentiate scopes)
   - Copy **all three redirect URLs** Alexa now shows (one per regional companion app -
     see `config.py`'s own comment on `alexa_redirect_uris`) into `ALEXA_REDIRECT_URIS`,
     comma-separated
4. Set `ALEXA_PUBLIC_URL`, `ALEXA_CLIENT_ID`, `ALEXA_CLIENT_SECRET`, `ALEXA_REDIRECT_URIS`,
   and `ALEXA_TOKEN_ENCRYPTION_KEY` (see `.env.example`).
5. In the Alexa app (or the console's Test tab), linking the account opens
   `/authorize`, which asks for the user's own StudyLife instance URL, then redirects to
   THAT instance's own login/consent page - approve it, and StudyLife redirects back
   through this server to Alexa.

## Deployment

Self-hosted (K3s + Tailscale Funnel), same pattern as
[studylife-mcp](https://github.com/lukislp/studylife-mcp)'s HTTP transport. Set
`ALEXA_VERIFY_REQUESTS=true` (the default) in any deployed environment - it's only ever
disabled for local testing with a hand-crafted, unsigned request body.

## Metrics

`GET /metrics` exposes Prometheus text-format metrics on the same port as everything
else (8000) - unauthenticated, same as
[studylife-mcp](https://github.com/lukislp/studylife-mcp)'s and
[studylife-ai](https://github.com/lukislp/studylife-ai)'s own `/metrics`. Process/platform
collectors (memory, GC, uptime) come for free from `prometheus_client`'s default registry;
this service adds five of its own:

| Metric | Type | Labels | Shows |
|---|---|---|---|
| `studylife_alexa_request_duration_seconds` | Histogram | `route`, `method` | HTTP latency per route |
| `studylife_alexa_requests_total` | Counter | `route`, `method`, `status_class` | HTTP request volume and status (`2xx`/`3xx`/`4xx`/`5xx`) |
| `studylife_alexa_upstream_requests_total` | Counter | `target`, `outcome` | Outbound-call volume to StudyLife, by outcome (`ok`/`http_error`/`failed`/`timeout`) |
| `studylife_alexa_upstream_request_duration_seconds` | Histogram | `target` | Outbound-call latency to StudyLife |
| `studylife_alexa_intents_total` | Counter | `intent`, `outcome` | Alexa intent/request volume and outcome (`ok`/`error`) |

`route` is always the matched route's own path template (never a raw path, so a 404 probe
can't inject unbounded label values) - unmatched paths are labeled `"unmatched"`. `target`
is always `"studylife-api"` today - every outbound call this service makes goes to
whatever StudyLife instance the caller linked their account against - kept as a label for
consistency with the sibling repos' own upstream metrics. `intent` is the bounded
intent/request name (e.g. `CoursesIntent`, `LaunchRequest`), never user utterance text or
slot values.

Scraped by the existing self-hosted Prometheus in the `homelab-infra` repo
(`monitoring/01-prometheus.yaml`), as part of the same telemetry rollout already covering
studylife-mcp and studylife-ai.

## Privacy & Terms

[PRIVACY.md](PRIVACY.md) / [TERMS.md](TERMS.md) - the URLs the Alexa Developer Console's
Distribution tab wants (link directly to the GitHub blob, e.g.
`https://github.com/lukislp/studylife-alexa/blob/main/PRIVACY.md` - no separate hosting
needed, same pattern as [studylife-capture](https://github.com/lukislp/studylife-capture)'s
own `PRIVACY.md`).

## License

AGPL-3.0
