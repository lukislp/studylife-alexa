"""Account-deletion purge route, OAuthStore.purge_by_key_hashes and the retention sweep."""

from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from studylife_alexa.config import Settings
from studylife_alexa.oauth_store import PENDING_AUTH_TTL_SECONDS, OAuthStore
from studylife_alexa.purge_routes import register_purge_routes
from studylife_alexa.retention import run_retention_sweep

_ENCRYPTION_KEY = "uIRpmPnsEoqKZQfaexXSeFjtrMGnBIrLa8mQBC09Jug="
_INSTANCE = "https://studylife.example.com"
_SECRET = "purge-secret"
_HEADERS = {"X-StudyLife-Shared-Secret": _SECRET}
_TOKEN_TABLES = (("auth_codes", "code"), ("access_tokens", "token"), ("refresh_tokens", "token"))


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _count(db_path, table: str) -> int:
    with sqlite3.connect(db_path) as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


async def _link(store: OAuthStore, api_key: str, suffix: str) -> None:
    await store.save_authorization_code(f"code-{suffix}", api_key, _INSTANCE)
    await store.save_access_token(f"access-{suffix}", api_key, _INSTANCE)
    await store.save_refresh_token(f"refresh-{suffix}", api_key, _INSTANCE)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "purge.db"


@pytest.fixture
def store(db_path) -> OAuthStore:
    store = OAuthStore(str(db_path), _ENCRYPTION_KEY)
    asyncio.run(store.initialize())
    return store


def _client(store: OAuthStore, secret: str | None) -> TestClient:
    app = FastAPI()
    register_purge_routes(app, store, Settings(studylife_purge_secret=secret))
    return TestClient(app)


def test_503_when_no_secret_is_configured(store) -> None:
    for secret in (None, ""):
        response = _client(store, secret).post(
            "/internal/users/1/purge", json={"key_hashes": []}, headers=_HEADERS
        )
        assert response.status_code == 503


@pytest.mark.parametrize("headers", [{}, {"X-StudyLife-Shared-Secret": "wrong"}])
def test_401_without_or_with_wrong_secret(store, headers) -> None:
    response = _client(store, _SECRET).post(
        "/internal/users/1/purge", json={"key_hashes": []}, headers=headers
    )
    assert response.status_code == 401


@pytest.mark.parametrize(
    "body",
    [
        {"key_hashes": ["short"]},
        {"key_hashes": [_sha("k").upper()]},
        {"key_hashes": [_sha(str(i)) for i in range(51)]},
        {"key_hashes": "nope"},
    ],
)
def test_422_for_invalid_key_hashes(store, body) -> None:
    response = _client(store, _SECRET).post("/internal/users/1/purge", json=body, headers=_HEADERS)
    assert response.status_code == 422


def test_422_for_non_integer_user_id(store) -> None:
    response = _client(store, _SECRET).post("/internal/users/abc/purge", json={}, headers=_HEADERS)
    assert response.status_code == 422


def test_204_deletes_only_matching_rows_and_is_idempotent(store, db_path) -> None:
    asyncio.run(_link(store, "key-alice", "a"))
    asyncio.run(_link(store, "key-bob", "b"))
    client = _client(store, _SECRET)

    for _ in range(2):  # the second call is a repeat: still 204, nothing more removed
        response = client.post(
            "/internal/users/7/purge",
            json={"key_hashes": [_sha("key-alice")]},
            headers=_HEADERS,
        )
        assert response.status_code == 204
        assert response.content == b""

    for table, _column in _TOKEN_TABLES:
        assert _count(db_path, table) == 1
    assert asyncio.run(store.load_access_token("access-a")) is None
    bob = asyncio.run(store.load_access_token("access-b"))
    assert bob is not None and bob.api_key == "key-bob"
    assert asyncio.run(store.consume_refresh_token("refresh-b")) is not None


def test_204_when_nothing_matches_or_body_is_empty(store, db_path) -> None:
    asyncio.run(_link(store, "key-bob", "b"))
    client = _client(store, _SECRET)

    unmatched = client.post(
        "/internal/users/7/purge", json={"key_hashes": [_sha("other")]}, headers=_HEADERS
    )
    empty = client.post("/internal/users/7/purge", json={}, headers=_HEADERS)

    assert unmatched.status_code == empty.status_code == 204
    assert _count(db_path, "access_tokens") == 1


def test_purge_matches_every_listed_hash(store, db_path) -> None:
    asyncio.run(_link(store, "key-1", "1"))
    asyncio.run(_link(store, "key-2", "2"))
    asyncio.run(_link(store, "key-3", "3"))

    deleted = asyncio.run(store.purge_by_key_hashes(frozenset({_sha("key-1"), _sha("key-2")})))

    assert deleted == 6
    assert _count(db_path, "access_tokens") == 1


def test_purge_skips_rows_it_cannot_decrypt(store, db_path) -> None:
    asyncio.run(_link(store, "key-1", "1"))
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE access_tokens SET encrypted_api_key = ?", (b"not-a-fernet-token",))
        db.commit()

    deleted = asyncio.run(store.purge_by_key_hashes(frozenset({_sha("key-1")})))

    assert deleted == 2  # code + refresh token; the undecryptable row is left to the sweep
    assert _count(db_path, "access_tokens") == 1


def _insert_expired_and_live(db_path) -> None:
    now = time.time()
    with sqlite3.connect(db_path) as db:
        for table, column in _TOKEN_TABLES:
            for name, expires_at in (("expired", now - 10), ("live", now + 1000)):
                db.execute(
                    f"INSERT INTO {table} ({column}, encrypted_api_key, studylife_instance_url, "
                    "expires_at) VALUES (?, ?, ?, ?)",
                    (name, b"x", _INSTANCE, expires_at),
                )
        for name, created_at in (
            ("stale", now - PENDING_AUTH_TTL_SECONDS - 10),
            ("fresh", now),
        ):
            db.execute(
                "INSERT INTO pending_auth (request_id, alexa_state, alexa_redirect_uri, "
                "studylife_instance_url, pkce_verifier, created_at) VALUES (?, '', '', ?, '', ?)",
                (name, _INSTANCE, created_at),
            )
        db.commit()


def test_delete_expired_removes_only_expired_rows(store, db_path) -> None:
    _insert_expired_and_live(db_path)

    deleted = asyncio.run(store.delete_expired())

    assert deleted == 4
    with sqlite3.connect(db_path) as db:
        for table, column in _TOKEN_TABLES:
            assert db.execute(f"SELECT {column} FROM {table}").fetchall() == [("live",)]
        assert db.execute("SELECT request_id FROM pending_auth").fetchall() == [("fresh",)]


def test_retention_sweep_runs_and_survives_a_failing_pass(store, db_path) -> None:
    _insert_expired_and_live(db_path)
    calls = 0
    real = store.delete_expired

    async def flaky() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        return await real()

    store.delete_expired = flaky  # type: ignore[method-assign]

    async def run() -> None:
        task = asyncio.create_task(run_retention_sweep(store, interval=0.01))
        await asyncio.sleep(0.2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())

    assert calls >= 2
    assert _count(db_path, "access_tokens") == 1
