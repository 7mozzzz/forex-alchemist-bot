"""Liquidity Inducement Theory (LIT) — detect liquidity sweeps and equal H/L pools.

Per the Alchemist + iscTrader material:
    - Liquidity Sweep ("LS") = wick that takes out a prior swing high/low but the
      candle closes back inside (rejection of the sweep).
    - Equal Highs / Equal Lows = stacked liquidity above/below price.
    - Inducement is the LAST opposite swing inside the current trend leg — every
      valid POI must have inducement preceding it.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .structure import Swing, SwingType


@dataclass
class LiquiditySweep:
    index: pd.Timestamp
    price: float
    direction: str  # "BUYSIDE" (sweeps a high) | "SELLSIDE" (sweeps a low)
    swept: Swing


@dataclass
class LiquidityPool:
    price: float
    direction: str  # "BUYSIDE" | "SELLSIDE"
    count: int
    last_touch: pd.Timestamp


def detect_sweeps(df: pd.DataFrame, swings: list[Swing], tolerance: float = 0.0005) -> list[LiquiditySweep]:
    """Return wicks that swept a prior swing but closed back inside."""
    sweeps: list[LiquiditySweep] = []
    if df.empty:
        return sweeps
    for swing in swings:
        future = df.loc[df.index > swing.index]
        if future.empty:
            continue
        if swing.type is SwingType.HIGH:
            wick_breach = future["high"] > swing.price * (1 + tolerance)
            close_inside = future["close"] < swing.price
            mask = wick_breach & close_inside
            if mask.any():
                ts = future.index[mask.argmax()]
                row = future.loc[ts]
                sweeps.append(
                    LiquiditySweep(
                        index=ts,
                        price=float(row["high"]),
                        direction="BUYSIDE",
                        swept=swing,
                    )
                )
        else:
            wick_breach = future["low"] < swing.price * (1 - tolerance)
            close_inside = future["close"] > swing.price
            mask = wick_breach & close_inside
            if mask.any():
                ts = future.index[mask.argmax()]
                row = future.loc[ts]
                sweeps.append(
                    LiquiditySweep(
                        index=ts,
                        price=float(row["low"]),
                        direction="SELLSIDE",
                        swept=swing,
                    )
                )
    return sweeps


def detect_equal_levels(swings: list[Swing], tolerance: float = 0.0008) -> list[LiquidityPool]:
    """Cluster swings whose prices are within `tolerance` of each other."""
    pools: list[LiquidityPool] = []
    highs = [s for s in swings if s.type is SwingType.HIGH]
    lows = [s for s in swings if s.type is SwingType.LOW]

    def _cluster(group: list[Swing], direction: str) -> list[LiquidityPool]:
        out: list[LiquidityPool] = []
        for i, s in enumerate(group):
            cluster = [s]
            for other in group[i + 1 :]:
                if abs(other.price - s.price) / s.price <= tolerance:
                    cluster.append(other)
            if len(cluster) >= 2:
                avg = sum(c.price for c in cluster) / len(cluster)
                last = max(c.index for c in cluster)
                out.append(
                    LiquidityPool(
                        price=avg,
                        direction=direction,
                        count=len(cluster),
                        last_touch=last,
                    )
                )
        return out

    pools.extend(_cluster(highs, "BUYSIDE"))
    pools.extend(_cluster(lows, "SELLSIDE"))
    # de-duplicate by rounded price
    seen: dict[tuple[float, str], LiquidityPool] = {}
    for p in pools:
        key = (round(p.price, 5), p.direction)
        if key not in seen or seen[key].count < p.count:
            seen[key] = p
    return list(seen.values())


def has_inducement(
    swings: list[Swing],
    poi_time: pd.Timestamp,
    poi_side: str,
    poi_price: float | None = None,
    current_price: float | None = None,
) -> bool:
    """LIT inducement check.

    For a BUY POI (support below price), inducement = an unswept swing LOW that
    sits between the POI and the current price. Price will sweep that low first
    (grabbing sellside liquidity) before tagging the POI.

    For a SELL POI, mirror: an unswept swing HIGH between the current price and
    the POI level.
    """
    target_type = SwingType.LOW if poi_side == "BUY" else SwingType.HIGH
    candidates = [s for s in swings if s.index > poi_time and s.type is target_type]

    if poi_price is None or current_price is None:
        return len(candidates) >= 1

    if poi_side == "BUY":
        # IDM low must be ABOVE the POI but below recent price action.
        in_range = [s for s in candidates if poi_price < s.price <= current_price * 1.02]
    else:
        in_range = [s for s in candidates if current_price * 0.98 <= s.price < poi_price]
    return len(in_range) >= 1
