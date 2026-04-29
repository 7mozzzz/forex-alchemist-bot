"""MSNR Key Levels detection.

Implements all six POI types from the S.Fx -1075 / Alchemist material:
    - Support  (Classic V) — buy POI
    - Resistance (Classic A / Apex) — sell POI
    - SBR      (Support Becomes Resistance) — sell POI after body break of support
    - RBS      (Resistance Becomes Support) — buy POI after body break of resistance
    - QML      (Quasimodo) — reversal POI after a 2x body break
    - OCL      (Open / Close Level) — body-only level from two same-color candles

A level is "Fresh" while it has not yet been mitigated (touched) by a later candle's body.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from .structure import Swing, SwingType


class LevelKind(StrEnum):
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"
    SBR = "SBR"
    RBS = "RBS"
    QML_BUY = "QML_BUY"
    QML_SELL = "QML_SELL"
    OCL_BUY = "OCL_BUY"
    OCL_SELL = "OCL_SELL"


BUY_KINDS = {LevelKind.SUPPORT, LevelKind.RBS, LevelKind.QML_BUY, LevelKind.OCL_BUY}
SELL_KINDS = {LevelKind.RESISTANCE, LevelKind.SBR, LevelKind.QML_SELL, LevelKind.OCL_SELL}


@dataclass
class KeyLevel:
    kind: LevelKind
    price: float
    created_at: pd.Timestamp
    fresh: bool = True
    notes: str = ""
    upper: float | None = None  # for OCL the body range upper bound
    lower: float | None = None  # for OCL the body range lower bound

    @property
    def side(self) -> str:
        return "BUY" if self.kind in BUY_KINDS else "SELL"

    def as_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "side": self.side,
            "price": self.price,
            "fresh": self.fresh,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }


def _is_bullish(row: pd.Series) -> bool:
    return float(row["close"]) > float(row["open"])


def _is_bearish(row: pd.Series) -> bool:
    return float(row["close"]) < float(row["open"])


def _body_high(row: pd.Series) -> float:
    return max(float(row["open"]), float(row["close"]))


def _body_low(row: pd.Series) -> float:
    return min(float(row["open"]), float(row["close"]))


def _classic_levels(swings: list[Swing]) -> list[KeyLevel]:
    """Pure Classic V (Support) / Classic A (Resistance) from swing pivots."""
    out: list[KeyLevel] = []
    for s in swings:
        if s.type is SwingType.HIGH:
            out.append(KeyLevel(LevelKind.RESISTANCE, s.price, s.index, notes=f"Classic A ({s.label})"))
        else:
            out.append(KeyLevel(LevelKind.SUPPORT, s.price, s.index, notes=f"Classic V ({s.label})"))
    return out


def _sbr_rbs_levels(df: pd.DataFrame, swings: list[Swing]) -> list[KeyLevel]:
    """A support broken by a bearish body becomes SBR (sell). Mirror for RBS."""
    out: list[KeyLevel] = []
    if df.empty:
        return out

    df["close"]
    df["open"]

    for swing in swings:
        if swing.index not in df.index:
            continue
        # Find first candle after the swing where the body breaks the level.
        future = df.loc[df.index > swing.index]
        if future.empty:
            continue
        if swing.type is SwingType.LOW:
            # Body close below the support level = break.
            mask = (future["close"] < swing.price) & (future["close"] < future["open"])
            if mask.any():
                ts = future.index[mask.argmax()]
                out.append(
                    KeyLevel(
                        kind=LevelKind.SBR,
                        price=swing.price,
                        created_at=ts,
                        notes=f"SBR — support {swing.price:.5f} broken by body",
                    )
                )
        else:
            mask = (future["close"] > swing.price) & (future["close"] > future["open"])
            if mask.any():
                ts = future.index[mask.argmax()]
                out.append(
                    KeyLevel(
                        kind=LevelKind.RBS,
                        price=swing.price,
                        created_at=ts,
                        notes=f"RBS — resistance {swing.price:.5f} broken by body",
                    )
                )
    return out


def _qml_levels(df: pd.DataFrame, swings: list[Swing]) -> list[KeyLevel]:
    """Quasimodo: support broken by 2 different body-closing candles, then nearest
    resistance also broken → QML BUY at the new HL. Mirror for QML SELL."""
    out: list[KeyLevel] = []
    highs = [s for s in swings if s.type is SwingType.HIGH]
    lows = [s for s in swings if s.type is SwingType.LOW]

    # QML BUY: LL (lower low) followed by HH (higher high than the LH between them)
    for i in range(2, len(lows)):
        prev_low = lows[i - 1]
        curr_low = lows[i]
        if curr_low.price >= prev_low.price:
            continue
        # find any high between them and a later high above it
        between_highs = [h for h in highs if prev_low.index < h.index < curr_low.index]
        later_highs = [h for h in highs if h.index > curr_low.index]
        if between_highs and later_highs:
            ref = between_highs[-1]
            for lh in later_highs:
                if lh.price > ref.price:
                    out.append(
                        KeyLevel(
                            kind=LevelKind.QML_BUY,
                            price=curr_low.price,
                            created_at=lh.index,
                            notes="QML BUY — bullish quasimodo formation",
                        )
                    )
                    break

    # QML SELL: HH followed by LL below the HL between them
    for i in range(2, len(highs)):
        prev_high = highs[i - 1]
        curr_high = highs[i]
        if curr_high.price <= prev_high.price:
            continue
        between_lows = [low for low in lows if prev_high.index < low.index < curr_high.index]
        later_lows = [low for low in lows if low.index > curr_high.index]
        if between_lows and later_lows:
            ref = between_lows[-1]
            for ll in later_lows:
                if ll.price < ref.price:
                    out.append(
                        KeyLevel(
                            kind=LevelKind.QML_SELL,
                            price=curr_high.price,
                            created_at=ll.index,
                            notes="QML SELL — bearish quasimodo formation",
                        )
                    )
                    break

    return out


def _ocl_levels(df: pd.DataFrame, lookback: int = 200) -> list[KeyLevel]:
    """OCL: two consecutive same-color candles whose bodies form a rejection level.
    Buy OCL = two bullish candles whose body-low acts as support.
    Sell OCL = two bearish candles whose body-high acts as resistance.
    """
    out: list[KeyLevel] = []
    if len(df) < 3:
        return out

    df_recent = df.iloc[-lookback:]
    rows = list(df_recent.iterrows())
    for i in range(1, len(rows)):
        ts_prev, prev = rows[i - 1]
        ts, curr = rows[i]
        if _is_bullish(prev) and _is_bullish(curr):
            level = min(_body_low(prev), _body_low(curr))
            upper = max(_body_low(prev), _body_low(curr))
            out.append(
                KeyLevel(
                    kind=LevelKind.OCL_BUY,
                    price=level,
                    upper=upper,
                    lower=level,
                    created_at=ts,
                    notes="OCL BUY — twin bullish bodies",
                )
            )
        elif _is_bearish(prev) and _is_bearish(curr):
            level = max(_body_high(prev), _body_high(curr))
            lower = min(_body_high(prev), _body_high(curr))
            out.append(
                KeyLevel(
                    kind=LevelKind.OCL_SELL,
                    price=level,
                    upper=level,
                    lower=lower,
                    created_at=ts,
                    notes="OCL SELL — twin bearish bodies",
                )
            )
    return out


def _mark_freshness(df: pd.DataFrame, levels: list[KeyLevel]) -> list[KeyLevel]:
    """A level is fresh while no later candle body has touched it after creation."""
    if df.empty:
        return levels
    for lvl in levels:
        future = df.loc[df.index > lvl.created_at]
        if future.empty:
            lvl.fresh = True
            continue
        body_high = future[["open", "close"]].max(axis=1)
        body_low = future[["open", "close"]].min(axis=1)
        if lvl.side == "BUY":
            mitigated = bool((body_low <= lvl.price).any())
        else:
            mitigated = bool((body_high >= lvl.price).any())
        lvl.fresh = not mitigated
    return levels


def find_key_levels(df: pd.DataFrame, swings: list[Swing]) -> list[KeyLevel]:
    """Public entrypoint — returns all MSNR key levels found in the dataframe,
    each marked as fresh (unmitigated) or used."""
    levels: list[KeyLevel] = []
    levels.extend(_classic_levels(swings))
    levels.extend(_sbr_rbs_levels(df, swings))
    levels.extend(_qml_levels(df, swings))
    levels.extend(_ocl_levels(df))
    levels = _mark_freshness(df, levels)
    levels.sort(key=lambda lvl: lvl.created_at)
    return levels


def nearest_levels(
    levels: list[KeyLevel],
    price: float,
    side: str,
    fresh_only: bool = True,
    n: int = 3,
) -> list[KeyLevel]:
    """Return the N nearest levels of the requested side relative to current price."""
    pool = [lvl for lvl in levels if lvl.side == side and (lvl.fresh or not fresh_only)]
    if side == "BUY":
        pool = [lvl for lvl in pool if lvl.price < price]
        pool.sort(key=lambda lvl: price - lvl.price)
    else:
        pool = [lvl for lvl in pool if lvl.price > price]
        pool.sort(key=lambda lvl: lvl.price - price)
    return pool[:n]
