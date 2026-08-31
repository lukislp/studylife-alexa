from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # amzn1.ask.skill.* from the Alexa Developer Console (Endpoint tab, or the skill's
    # own manifest) - checked against every incoming request's applicationId so this
    # endpoint only ever answers requests for this one skill, not any other skill that
    # happened to learn its URL.
    alexa_skill_id: str

    # Signature/timestamp verification requires a real Alexa-signed request (a valid
    # SignatureCertChainUrl pointing at Amazon's own cert). Only ever False for local
    # testing with a hand-crafted request body - never disable this in a deployed
    # environment, or anyone who finds the URL can send it forged requests.
    alexa_verify_requests: bool = True

    # --- Account linking (oauth_provider.py) - all optional, with no bearing on the
    # Phase A/B canned-response handlers, which never read them. Only required once a
    # StudyLife-backed intent needs get_account_linking_access_token(handler_input) to
    # resolve to a real StudyLife API key.

    # This server's own public base URL (the Tailscale Funnel hostname) - authorize()
    # needs it to build the callback URL StudyLife's connect flow redirects back to.
    alexa_public_url: AnyHttpUrl | None = None

    # Issued by this server, entered directly into the Alexa Developer Console's Account
    # Linking config (Client ID / Client Secret fields) - these authenticate Alexa's own
    # backend to this server's /token endpoint, NOT a StudyLife credential. Generate with
    # `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
    alexa_client_id: str | None = None
    alexa_client_secret: str | None = None

    # Comma-separated exact redirect_uri values Alexa's Account Linking config page
    # shows once Client ID/Secret are filled in - THREE fixed values per skill, one per
    # Alexa companion-app region (pitangui.amazon.com/US, layla.amazon.com,
    # alexa.amazon.co.jp/Japan), not just one. Which one Alexa actually sends on a given
    # /authorize call depends on which regional app/site the user is linking from, so
    # authorize() has to accept any of them - not a single fixed value the way
    # studylife-cli's own AllowedRedirectUris registration gets away with (a native
    # app has exactly one redirect target, a skill has three).
    alexa_redirect_uris: str | None = None

    # Multi-tenant: every user picks THEIR OWN StudyLife instance's URL during
    # authorize() (see oauth_provider.py's instance-selection form) - there is no
    # longer one fixed instance this server always redirects to. This setting is only
    # a convenience default, pre-filling that form's input field so the deployer's own
    # instance doesn't need retyping every time; every other user simply overwrites it.
    # Kept as one field, not a connect/base_url split like earlier revisions had - both
    # the browser (StudyLife's login/consent page) and this server's own
    # assertion-exchange call now hit the same per-user URL the form collected, so
    # there's nothing left to split.
    studylife_default_instance_url: AnyHttpUrl | None = None

    # Fernet key (32 url-safe base64-encoded bytes, e.g. via
    # `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`)
    # encrypting the StudyLife API key at rest in oauth_store.py - this server needs the
    # plaintext back to call StudyLife on the user's behalf, so hashing alone isn't an
    # option here.
    alexa_token_encryption_key: str | None = None

    # SQLite file for the account-linking OAuth store (oauth_store.py). Relative to the
    # working directory unless absolute; gitignored like .env.
    alexa_oauth_db_path: str = "oauth.db"
