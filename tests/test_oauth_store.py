"""Covers OAuthStore.initialize()'s in-place schema migration - see its own comment on
_TABLES_NEEDING_INSTANCE_URL_MIGRATION for why CREATE TABLE IF NOT EXISTS alone isn't
enough for an upgrade-in-place from a pre-multi-tenant database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from studylife_alexa.oauth_store import OAuthStore

_PRE_MIGRATION_SCHEMA = """
CREATE TABLE pending_auth (
    request_id TEXT PRIMARY KEY,
    alexa_state TEXT NOT NULL,
    alexa_redirect_uri TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE auth_codes (
    code TEXT PRIMARY KEY,
    encrypted_api_key BLOB NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE access_tokens (
    token TEXT PRIMARY KEY,
    encrypted_api_key BLOB NOT NULL,
    expires_at REAL NOT NULL
);
CREATE TABLE refresh_tokens (
    token TEXT PRIMARY KEY,
    encrypted_api_key BLOB NOT NULL,
    expires_at REAL NOT NULL
);
"""

_ENCRYPTION_KEY = "uIRpmPnsEoqKZQfaexXSeFjtrMGnBIrLa8mQBC09Jug="


def _make_pre_migration_db(path: Path) -> None:
    with sqlite3.connect(path) as db:
        db.executescript(_PRE_MIGRATION_SCHEMA)
        db.commit()


async def test_initialize_migrates_pre_multi_tenant_database(tmp_path) -> None:
    db_path = tmp_path / "pre_migration.db"
    _make_pre_migration_db(db_path)

    store = OAuthStore(str(db_path), _ENCRYPTION_KEY)
    await store.initialize()  # must not raise

    with sqlite3.connect(db_path) as db:
        for table in ("pending_auth", "auth_codes", "access_tokens", "refresh_tokens"):
            columns = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            assert "studylife_instance_url" in columns


async def test_initialize_is_idempotent_on_an_already_migrated_database(tmp_path) -> None:
    db_path = tmp_path / "already_migrated.db"

    store = OAuthStore(str(db_path), _ENCRYPTION_KEY)
    await store.initialize()
    await store.initialize()  # running twice must not raise (no duplicate ALTER TABLE)

    await store.save_access_token("tok", "key", "https://studylife.example.com")
    linked = await store.load_access_token("tok")
    assert linked is not None
    assert linked.base_url == "https://studylife.example.com"


async def test_pre_migration_row_reads_back_with_empty_base_url(tmp_path) -> None:
    """A token saved before the migration ran has no real instance URL to recover -
    reads back as an empty string rather than crashing, so the caller can detect it and
    prompt a re-link instead of getting an unhandled error deep in an HTTP call."""
    db_path = tmp_path / "pre_migration_with_row.db"
    _make_pre_migration_db(db_path)

    from cryptography.fernet import Fernet

    encrypted = Fernet(_ENCRYPTION_KEY.encode()).encrypt(b"pre-migration-api-key")
    with sqlite3.connect(db_path) as db:
        db.execute(
            "INSERT INTO access_tokens (token, encrypted_api_key, expires_at) VALUES (?, ?, ?)",
            ("pre-migration-token", encrypted, 9_999_999_999.0),
        )
        db.commit()

    store = OAuthStore(str(db_path), _ENCRYPTION_KEY)
    await store.initialize()

    linked = await store.load_access_token("pre-migration-token")
    assert linked is not None
    assert linked.api_key == "pre-migration-api-key"
    assert linked.base_url == ""
