"""Hourly retention sweep: bounds how long expired codes and tokens stay in the database
(PRIVACY.md, "Data retention"). Same pattern as studylife-mcp's run_periodic_cleanup."""

from __future__ import annotations

import asyncio
import logging

from studylife_alexa.oauth_store import OAuthStore

logger = logging.getLogger(__name__)

SWEEP_INTERVAL_SECONDS = 60 * 60


async def run_retention_sweep(store: OAuthStore, interval: float = SWEEP_INTERVAL_SECONDS) -> None:
    """Runs forever (the caller cancels it on shutdown). A failed sweep is logged and
    retried on the next tick instead of ending the loop."""
    while True:
        try:
            deleted = await store.delete_expired()
            if deleted:
                logger.info("retention sweep deleted_rows=%s", deleted)
        except Exception:
            logger.exception("retention sweep failed")
        await asyncio.sleep(interval)
