"""Tests for MSNR key-level detection."""
from __future__ import annotations

import numpy as np
import pandas as pd

from alchemist_bot.strategy.levels import LevelKind, find_key_levels, nearest_levels
from alchemist_bot.strategy.structure import analyze_structure


def _df(prices: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(prices), freq="h", tz="UTC")
    arr = np.array(prices, dtype=float)
    return pd.DataFrame(
        {
            "open": arr,
            "high": arr + 0.3,
            "low": arr - 0.3,
            "close": arr,
            "volume": 0,
        },
        index=idx,
    )


_ZIGZAG = [
    1.00, 1.05, 1.10, 1.05, 1.00,
    0.95, 0.90, 0.95, 1.00, 1.05,
    1.10, 1.15, 1.20, 1.15, 1.10,
    1.05, 1.00, 1.05, 1.10, 1.15,
]


def test_levels_found_for_swing_series() -> None:
    df = _df(_ZIGZAG)
    snap = analyze_structure(df)
    levels = find_key_levels(df, snap.swings)
    kinds = {lv.kind for lv in levels}
    assert LevelKind.SUPPORT in kinds or LevelKind.RESISTANCE in kinds


def test_nearest_returns_below_for_buy() -> None:
    df = _df(_ZIGZAG)
    snap = analyze_structure(df)
    levels = find_key_levels(df, snap.swings)
    near = nearest_levels(levels, price=1.30, side="BUY", fresh_only=False, n=2)
    for lv in near:
        assert lv.price < 1.30
        assert lv.side == "BUY"
