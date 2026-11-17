"""Account-deletion purge route (GDPR Art. 17).

When a StudyAtrium account is deleted, the server calls
`POST /internal/users/{user_id}/purge` with the SHA-256 hashes of the API keys it issued to
this add-on for that user. The route is secret-protected, answers 503 while no secret is
configured, and is never exposed on the public Funnel (k8s/05-tailscale-funnel.yaml). The
deletion itself lives in OAuthStore.purge_by_key_hashes; this module only handles HTTP.
"""

from __future__ import annotations

import hmac
import logging
import re
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from studylife_alexa.config import Settings
from studylife_alexa.oauth_store import OAuthStore

logger = logging.getLogger(__name__)

MAX_KEY_HASHES = 50
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


class PurgeRequest(BaseModel):
    key_hashes: Annotated[list[str], Field(max_length=MAX_KEY_HASHES)] = []

    @field_validator("key_hashes")
    @classmethod
    def _each_is_sha256_hex(cls, value: list[str]) -> list[str]:
        if not all(_SHA256_HEX.fullmatch(item) for item in value):
            raise ValueError("each key hash must be 64 lowercase hex characters")
        return value


def register_purge_routes(app: FastAPI, store: OAuthStore, settings: Settings) -> None:
    @app.post("/internal/users/{user_id}/purge", status_code=204)
    async def purge_user(
        user_id: int,
        body: PurgeRequest,
        x_studylife_shared_secret: Annotated[str | None, Header()] = None,
    ) -> Response:
        secret = settings.studylife_purge_secret
        if not secret:
            raise HTTPException(status_code=503, detail="purge is not configured")
        if x_studylife_shared_secret is None or not hmac.compare_digest(
            x_studylife_shared_secret.encode(), secret.encode()
        ):
            raise HTTPException(status_code=401, detail="unauthorized")

        deleted = await store.purge_by_key_hashes(frozenset(body.key_hashes))
        logger.info("account purge user_id=%s deleted_rows=%s", user_id, deleted)
        return Response(status_code=204)
