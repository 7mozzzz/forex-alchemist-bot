"""Tests for the market-structure module."""
from __future__ import annotations

import numpy as np
import pandas as pd

from alchemist_bot.strategy.structure import Trend, analyze_structure, atr


def _make_df(closes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(closes), freq="h", tz="UTC")
    closes_arr = np.array(closes, dtype=float)
    df = pd.DataFrame(
        {
            "open": closes_arr,
            "high": closes_arr + 0.5,
            "low": closes_arr - 0.5,
            "close": closes_arr,
            "volume": 0,
        },
        index=idx,
    )
    return df


def test_returns_empty_for_short_series() -> None:
    df = _make_df([1.0, 1.1, 1.2])
    snap = analyze_structure(df)
    assert snap.swings == []
    assert snap.events == []
    assert snap.trend is Trend.RANGING


def test_detects_swings_in_zigzag() -> None:
    # Distinct swings, each separated by enough bars to satisfy left=right=2.
    closes = [
        1.00, 1.05, 1.10, 1.05, 1.00,   # swing high at idx 2
        0.95, 0.90, 0.95, 1.00, 1.05,   # swing low at idx 6
        1.10, 1.15, 1.20, 1.15, 1.10,   # swing high at idx 12
        1.05, 1.00, 1.05, 1.10, 1.15,
    ]
    df = _make_df(closes)
    snap = analyze_structure(df)
    assert any(s.type.value == "HIGH" for s in snap.swings)
    assert any(s.type.value == "LOW" for s in snap.swings)


def test_atr_handles_short_series() -> None:
    df = _make_df([1.0, 1.05, 1.1])
    value = atr(df, period=14)
    assert value > 0
