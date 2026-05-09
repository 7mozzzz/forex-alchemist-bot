"""Market Structure analysis: swing points, HH/HL/LH/LL, BOS, CHOCH, Inducement.

Implements the SMC + LIT rules from the Alchemist material:
    - Swings detected via fractal pivot
    - Break of Structure (BOS) when price closes beyond the most recent confirmed swing
    - Change of Character (CHOCH) when an opposite swing is broken (trend reversal)
    - Inducement (IDM) = the most recent valid pullback inside the current trend leg;
      every POI must be preceded by inducement.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd


class SwingType(StrEnum):
    HIGH = "HIGH"
    LOW = "LOW"


class Trend(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGING = "RANGING"


@dataclass
class Swing:
    index: pd.Timestamp
    price: float
    type: SwingType
    label: str = ""  # HH / HL / LH / LL


@dataclass
class StructureEvent:
    index: pd.Timestamp
    price: float
    kind: str  # "BOS" | "CHOCH"
    direction: str  # "BULLISH" | "BEARISH"
    swing_broken: Swing


@dataclass
class StructureSnapshot:
    swings: list[Swing]
    events: list[StructureEvent]
    trend: Trend
    last_inducement: Swing | None
    current_high: Swing | None
    current_low: Swing | None


def _fractal_pivots(df: pd.DataFrame, left: int = 2, right: int = 2) -> list[Swing]:
    """Detect raw fractal pivot highs/lows."""
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    times = df.index
    swings: list[Swing] = []
    for i in range(left, len(df) - right):
        window_high = highs[i - left : i + right + 1]
        window_low = lows[i - left : i + right + 1]
        if highs[i] == window_high.max() and (window_high.argmax() == left):
            swings.append(Swing(index=times[i], price=float(highs[i]), type=SwingType.HIGH))
        if lows[i] == window_low.min() and (window_low.argmin() == left):
            swings.append(Swing(index=times[i], price=float(lows[i]), type=SwingType.LOW))
    swings.sort(key=lambda s: s.index)
    return swings


def _label_swings(swings: list[Swing]) -> list[Swing]:
    """Tag each swing as HH / HL / LH / LL relative to the previous same-type swing."""
    last_high: Swing | None = None
    last_low: Swing | None = None
    for s in swings:
        if s.type is SwingType.HIGH:
            if last_high is None:
                s.label = "H"
            else:
                s.label = "HH" if s.price > last_high.price else "LH"
            last_high = s
        else:
            if last_low is None:
                s.label = "L"
            else:
                s.label = "HL" if s.price > last_low.price else "LL"
            last_low = s
    return swings


def _detect_events(df: pd.DataFrame, swings: list[Swing]) -> tuple[list[StructureEvent], Trend]:
    """Walk forward through closes, detect BOS / CHOCH on body-close break."""
    events: list[StructureEvent] = []
    trend = Trend.RANGING
    last_high: Swing | None = None
    last_low: Swing | None = None

    swings_iter = iter(swings)
    next_swing = next(swings_iter, None)

    for ts, row in df.iterrows():
        close = float(row["close"])
        # Push any swings whose timestamp is at/before this candle
        while next_swing is not None and next_swing.index <= ts:
            if next_swing.type is SwingType.HIGH:
                last_high = next_swing
            else:
                last_low = next_swing
            next_swing = next(swings_iter, None)

        if last_high is not None and close > last_high.price:
            kind = "CHOCH" if trend is Trend.BEARISH else "BOS"
            events.append(
                StructureEvent(
                    index=ts,
                    price=close,
                    kind=kind,
                    direction="BULLISH",
                    swing_broken=last_high,
                )
            )
            trend = Trend.BULLISH
            last_high = None  # consumed
        elif last_low is not None and close < last_low.price:
            kind = "CHOCH" if trend is Trend.BULLISH else "BOS"
            events.append(
                StructureEvent(
                    index=ts,
                    price=close,
                    kind=kind,
                    direction="BEARISH",
                    swing_broken=last_low,
                )
            )
            trend = Trend.BEARISH
            last_low = None

    return events, trend


def analyze_structure(
    df: pd.DataFrame,
    left: int = 2,
    right: int = 2,
) -> StructureSnapshot:
    """Run the full structure pipeline on a DataFrame of OHLC candles."""
    if len(df) < (left + right + 5):
        return StructureSnapshot(swings=[], events=[], trend=Trend.RANGING,
                                  last_inducement=None, current_high=None, current_low=None)

    raw = _fractal_pivots(df, left=left, right=right)
    labeled = _label_swings(raw)
    events, trend = _detect_events(df, labeled)

    current_high = next((s for s in reversed(labeled) if s.type is SwingType.HIGH), None)
    current_low = next((s for s in reversed(labeled) if s.type is SwingType.LOW), None)

    # Inducement = the most recent opposite-side swing that price has not yet swept.
    # In a bullish leg, IDM = most recent low between the swing low and current price.
    last_inducement: Swing | None = None
    if trend is Trend.BULLISH and current_low is not None:
        last_inducement = current_low
    elif trend is Trend.BEARISH and current_high is not None:
        last_inducement = current_high

    return StructureSnapshot(
        swings=labeled,
        events=events,
        trend=trend,
        last_inducement=last_inducement,
        current_high=current_high,
        current_low=current_low,
    )


def atr(df: pd.DataFrame, period: int = 14) -> float:
    """Classic ATR — used to size SL when no clear key level is below/above entry."""
    if len(df) < period + 1:
        return float(df["close"].iloc[-1] * 0.001)
    high = df["high"].to_numpy()
    low = df["low"].to_numpy()
    close = df["close"].to_numpy()
    prev_close = np.concatenate(([close[0]], close[:-1]))
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    return float(pd.Series(tr).rolling(period).mean().iloc[-1])
