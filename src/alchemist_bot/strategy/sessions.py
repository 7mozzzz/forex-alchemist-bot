"""ICT Time Sessions / Kill Zones.

Sessions (UTC, approximate ICT definitions):
    Asia  : 23:00 → 06:00 (Sydney + Tokyo overlap)
    London: 07:00 → 10:00 (London Kill Zone)
    NY AM : 12:00 → 15:00 (New York AM Kill Zone)
    NY PM : 18:00 → 21:00 (New York PM Kill Zone)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time

import pandas as pd


@dataclass
class Session:
    name: str
    start: time
    end: time
    is_kill_zone: bool

    def contains(self, dt: datetime) -> bool:
        t = dt.astimezone(UTC).time()
        if self.start <= self.end:
            return self.start <= t < self.end
        # wraps midnight
        return t >= self.start or t < self.end


SESSIONS: list[Session] = [
    Session("Asia", time(23, 0), time(6, 0), is_kill_zone=False),
    Session("London KZ", time(7, 0), time(10, 0), is_kill_zone=True),
    Session("NY AM KZ", time(12, 0), time(15, 0), is_kill_zone=True),
    Session("NY PM KZ", time(18, 0), time(21, 0), is_kill_zone=True),
]


def current_session(now: datetime | None = None) -> Session | None:
    now = now or datetime.now(UTC)
    for s in SESSIONS:
        if s.contains(now):
            return s
    return None


@dataclass
class AsiaRange:
    high: float
    low: float
    high_time: pd.Timestamp
    low_time: pd.Timestamp


def asia_range(df_h1: pd.DataFrame, today: pd.Timestamp | None = None) -> AsiaRange | None:
    """Compute Asia session H/L from an H1 dataframe (UTC)."""
    if df_h1.empty:
        return None
    today = today or pd.Timestamp.utcnow().normalize()
    # Asia = previous day 23:00 → today 06:00 UTC
    start = today - pd.Timedelta(hours=1)  # yesterday 23:00
    end = today + pd.Timedelta(hours=6)
    window = df_h1.loc[(df_h1.index >= start) & (df_h1.index < end)]
    if window.empty:
        # fallback: take the last 7 hourly candles
        window = df_h1.iloc[-7:]
    high = float(window["high"].max())
    low = float(window["low"].min())
    return AsiaRange(
        high=high,
        low=low,
        high_time=window["high"].idxmax(),
        low_time=window["low"].idxmin(),
    )
