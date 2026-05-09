"""Tests for Daye Quarterly Theory cycle calculator."""
from __future__ import annotations

from datetime import UTC, datetime

from alchemist_bot.strategy.quarterly import current_quarters, directional_bias


def test_current_quarters_returns_all_cycles() -> None:
    now = datetime(2025, 4, 15, 13, 30, tzinfo=UTC)
    qs = current_quarters(now)
    cycles = {q.cycle for q in qs}
    assert {"Yearly", "Monthly", "Weekly", "Daily", "90min"} <= cycles


def test_yearly_quarter_april() -> None:
    now = datetime(2025, 4, 15, 13, 30, tzinfo=UTC)
    qs = {q.cycle: q for q in current_quarters(now)}
    assert qs["Yearly"].q == 2  # April → Q2


def test_directional_bias_text() -> None:
    assert "RANGING" in directional_bias(1)
    assert "MANIPULATION" in directional_bias(2)
    assert "EXPANSION" in directional_bias(3)
    assert "DECISION" in directional_bias(4)
