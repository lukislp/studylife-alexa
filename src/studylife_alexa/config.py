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
