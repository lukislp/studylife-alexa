# studylife-alexa

Alexa Skill backend for [StudyLife](https://github.com/lukislp/studylife): voice control for
the focus timer and study sessions, account-linked to your own StudyLife instance.

## Status

- `LaunchRequest` - welcome message
- `TestIntent` - confirms the connection is working, no account needed
- `CoursesIntent` - the first real StudyLife-backed intent ("wie viele Kurse habe ich"),
  proving account linking end to end
- `AMAZON.HelpIntent` / `AMAZON.CancelIntent` / `AMAZON.StopIntent` - built-ins

More StudyLife-backed intents (focus timer status/start, study time) come next.

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

1. Register this skill as an ordinary add-on on your own
   [studylife-developers](https://github.com/lukislp/studylife-developers) instance:
   **Client ID**: `studylife-alexa`, **Allowed redirect URIs**:
   `https://<your-public-url>/oauth/studylife/callback`, whichever scopes you want the
   skill to use.
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
   - Copy the **redirect URL(s)** Alexa now shows into `ALEXA_REDIRECT_URI`
4. Set `ALEXA_PUBLIC_URL`, `ALEXA_CLIENT_ID`, `ALEXA_CLIENT_SECRET`, `ALEXA_REDIRECT_URI`,
   `STUDYLIFE_CONNECT_URL`, `STUDYLIFE_BASE_URL`, and `ALEXA_TOKEN_ENCRYPTION_KEY` (see
   `.env.example`).
5. In the Alexa app (or the console's Test tab), linking the account opens
   `/authorize`, which redirects to StudyLife's own login/consent page - approve it,
   and StudyLife redirects back through this server to Alexa.

## Deployment

Self-hosted (K3s + Tailscale Funnel), same pattern as
[studylife-mcp](https://github.com/lukislp/studylife-mcp)'s HTTP transport. Set
`ALEXA_VERIFY_REQUESTS=true` (the default) in any deployed environment - it's only ever
disabled for local testing with a hand-crafted, unsigned request body.

## License

AGPL-3.0
