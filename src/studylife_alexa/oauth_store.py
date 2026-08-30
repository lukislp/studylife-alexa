"""SQLite-backed persistence for the account-linking OAuth wrapper (oauth_provider.py).

Much simpler than studylife-mcp's own oauth_store.py: Alexa is one single, fixed,
pre-registered client (no RFC 7591 dynamic client registration, no per-client scoping,
no /connected-apps self-service page) - just four short-lived-to-long-lived lookups,
each mapping an opaque token this server minted to the underlying StudyLife API key,
encrypted at rest the same way (Fernet) since this server needs the plaintext back to
call StudyLife on the user's behalf.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

import aiosqlite
from cryptography.fernet import Fernet

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_auth (
    request_id TEXT PRIMARY KEY,
    alexa_state TEXT NOT NULL,
    alexa_redirect_uri TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_codes (
    code TEXT PRIMARY KEY,
    encrypted_api_key BLOB NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS access_tokens (
    token TEXT PRIMARY KEY,
    encrypted_api_key BLOB NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token TEXT PRIMARY KEY,
    encrypted_api_key BLOB NOT NULL,
    expires_at REAL NOT NULL
);
"""

# How long a /authorize -> StudyLife connect flow round trip has to complete before the
# pending request is discarded. Generous for a human logging in once.
PENDING_AUTH_TTL_SECONDS = 600

# 5 minutes to complete the code -> token exchange (RFC 6749 recommends a short window).
AUTHORIZATION_CODE_TTL_SECONDS = 300

ACCESS_TOKEN_TTL_SECONDS = 60 * 60  # 1 hour
REFRESH_TOKEN_TTL_SECONDS = 60 * 60 * 24 * 90  # 90 days, rotated on every use


@dataclass(frozen=True)
class PendingAuthorization:
    alexa_state: str
    alexa_redirect_uri: str


class OAuthStore:
    def __init__(self, db_path: str, encryption_key: str) -> None:
        self._db_path = db_path
        self._fernet = Fernet(encryption_key.encode())

    async def initialize(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    # --- authorize() -> StudyLife connect flow round trip ---

    async def save_pending_authorization(
        self, request_id: str, *, alexa_state: str, alexa_redirect_uri: str
    ) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO pending_auth "
                "(request_id, alexa_state, alexa_redirect_uri, created_at) VALUES (?, ?, ?, ?)",
                (request_id, alexa_state, alexa_redirect_uri, time.time()),
            )
            await db.commit()

    async def consume_pending_authorization(self, request_id: str) -> PendingAuthorization | None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT alexa_state, alexa_redirect_uri, created_at FROM pending_auth "
                "WHERE request_id = ?",
                (request_id,),
            )
            row = await cursor.fetchone()
            await db.execute("DELETE FROM pending_auth WHERE request_id = ?", (request_id,))
            await db.commit()

        if row is None:
            return None
        alexa_state, alexa_redirect_uri, created_at = row
        if created_at + PENDING_AUTH_TTL_SECONDS < time.time():
            return None
        return PendingAuthorization(alexa_state=alexa_state, alexa_redirect_uri=alexa_redirect_uri)

    # --- authorization code -> token exchange ---

    async def save_authorization_code(self, code: str, studylife_api_key: str) -> None:
        encrypted = self._fernet.encrypt(studylife_api_key.encode())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO auth_codes (code, encrypted_api_key, expires_at) "
                "VALUES (?, ?, ?)",
                (code, encrypted, time.time() + AUTHORIZATION_CODE_TTL_SECONDS),
            )
            await db.commit()

    async def consume_authorization_code(self, code: str) -> str | None:
        """Single-use (RFC 6749 SS10.5) - deleted whether or not it turns out to still be
        valid, so a replayed code can never succeed twice."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT encrypted_api_key, expires_at FROM auth_codes WHERE code = ?", (code,)
            )
            row = await cursor.fetchone()
            await db.execute("DELETE FROM auth_codes WHERE code = ?", (code,))
            await db.commit()

        if row is None:
            return None
        encrypted_api_key, expires_at = row
        if expires_at < time.time():
            return None
        return self._fernet.decrypt(encrypted_api_key).decode()

    # --- access / refresh tokens ---

    async def save_access_token(self, token: str, studylife_api_key: str) -> None:
        encrypted = self._fernet.encrypt(studylife_api_key.encode())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO access_tokens (token, encrypted_api_key, expires_at) "
                "VALUES (?, ?, ?)",
                (token, encrypted, time.time() + ACCESS_TOKEN_TTL_SECONDS),
            )
            await db.commit()

    async def load_access_token(self, token: str) -> str | None:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT encrypted_api_key, expires_at FROM access_tokens WHERE token = ?",
                (token,),
            )
            row = await cursor.fetchone()

        if row is None:
            return None
        encrypted_api_key, expires_at = row
        if expires_at < time.time():
            return None
        return self._fernet.decrypt(encrypted_api_key).decode()

    async def save_refresh_token(self, token: str, studylife_api_key: str) -> None:
        encrypted = self._fernet.encrypt(studylife_api_key.encode())
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO refresh_tokens (token, encrypted_api_key, expires_at) "
                "VALUES (?, ?, ?)",
                (token, encrypted, time.time() + REFRESH_TOKEN_TTL_SECONDS),
            )
            await db.commit()

    async def consume_refresh_token(self, token: str) -> str | None:
        """Rotate on use: the old refresh token stops working the moment it's exchanged."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT encrypted_api_key, expires_at FROM refresh_tokens WHERE token = ?",
                (token,),
            )
            row = await cursor.fetchone()
            await db.execute("DELETE FROM refresh_tokens WHERE token = ?", (token,))
            await db.commit()

        if row is None:
            return None
        encrypted_api_key, expires_at = row
        if expires_at < time.time():
            return None
        return self._fernet.decrypt(encrypted_api_key).decode()


def load_access_token_sync(db_path: str, encryption_key: str, token: str) -> str | None:
    """Plain sqlite3 (not aiosqlite) counterpart to OAuthStore.load_access_token, for
    handlers.py's use: ask-sdk-core's RequestHandler.handle() is a synchronous callback
    (its dispatcher has no async hook at all - it was originally designed for AWS
    Lambda's sync handler model), so it can't await the async store used everywhere
    else. A short-lived sqlite3 connection reading the same file is safe alongside the
    aiosqlite connections the FastAPI routes use - SQLite handles concurrent readers
    natively, and this path never writes."""
    with sqlite3.connect(db_path) as db:
        row = db.execute(
            "SELECT encrypted_api_key, expires_at FROM access_tokens WHERE token = ?", (token,)
        ).fetchone()

    if row is None:
        return None
    encrypted_api_key, expires_at = row
    if expires_at < time.time():
        return None
    return Fernet(encryption_key.encode()).decrypt(encrypted_api_key).decode()
