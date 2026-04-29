"""Tests for the ICT session helpers."""
from __future__ import annotations

from datetime import UTC, datetime

from alchemist_bot.strategy.sessions import current_session


def test_london_kill_zone() -> None:
    dt = datetime(2025, 4, 15, 8, 0, tzinfo=UTC)
    sess = current_session(dt)
    assert sess is not None
    assert sess.is_kill_zone


def test_off_hours_returns_none() -> None:
    dt = datetime(2025, 4, 15, 11, 0, tzinfo=UTC)  # between London and NY
    sess = current_session(dt)
    assert sess is None or not sess.is_kill_zone
