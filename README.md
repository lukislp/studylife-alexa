# studylife-alexa

Alexa Skill backend for [StudyLife](https://github.com/lukislp/studylife): voice control for
the focus timer and study sessions, account-linked to your own StudyLife instance.

## Status: Phase A (skeleton)

The skill currently only proves out the endpoint pipeline - signature verification, skill-ID
check, deployment - with canned responses and no StudyLife API calls yet:

- `LaunchRequest` - welcome message
- `TestIntent` - confirms the connection is working
- `AMAZON.HelpIntent` / `AMAZON.CancelIntent` / `AMAZON.StopIntent` - built-ins

Real StudyLife-backed intents (focus timer status/start, study time) and account linking
(OAuth wrapper around StudyLife's own connect flow) come next.

## Development

```bash
uv sync
cp .env.example .env   # fill in ALEXA_SKILL_ID from the Alexa Developer Console
uv run uvicorn studylife_alexa.main:app --reload
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Deployment

Self-hosted (K3s + Tailscale Funnel), same pattern as
[studylife-mcp](https://github.com/lukislp/studylife-mcp)'s HTTP transport. Set
`ALEXA_VERIFY_REQUESTS=true` (the default) in any deployed environment - it's only ever
disabled for local testing with a hand-crafted, unsigned request body.

## License

AGPL-3.0
