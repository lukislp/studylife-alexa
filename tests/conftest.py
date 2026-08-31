import os
from pathlib import Path

os.environ["ALEXA_SKILL_ID"] = "amzn1.ask.skill.test"
os.environ["ALEXA_VERIFY_REQUESTS"] = "false"

os.environ["ALEXA_PUBLIC_URL"] = "https://studylife-alexa.example.com"
os.environ["ALEXA_CLIENT_ID"] = "test-alexa-client-id"
os.environ["ALEXA_CLIENT_SECRET"] = "test-alexa-client-secret"
os.environ["ALEXA_REDIRECT_URIS"] = (
    "https://pitangui.amazon.com/api/skill/link/TEST,"
    "https://layla.amazon.com/api/skill/link/TEST,"
    "https://alexa.amazon.co.jp/api/skill/link/TEST"
)
# A real (if throwaway) Fernet key, not the module's own random-fallback - deterministic
# across test runs, and exercises the same code path production actually uses.
os.environ["ALEXA_TOKEN_ENCRYPTION_KEY"] = "uIRpmPnsEoqKZQfaexXSeFjtrMGnBIrLa8mQBC09Jug="

_TEST_DB_PATH = Path(__file__).parent / "test_oauth.db"
_TEST_DB_PATH.unlink(missing_ok=True)
os.environ["ALEXA_OAUTH_DB_PATH"] = str(_TEST_DB_PATH)

# The instance URL most tests link their fake account against (multi-tenant means each
# linked account can carry its own distinct instance URL - this is just the
# common-case default for tests that don't care which one).
TEST_INSTANCE_URL = "https://studylife.example.com"
