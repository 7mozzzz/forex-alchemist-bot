"""Quarterly Theory (Daye QT) — A·M·D·X cycles.

Each cycle has 4 Quarters:
    Q1 = Accumulation (A)
    Q2 = Manipulation (M)
    Q3 = Distribution (D)
    Q4 = Continuation / Reversal (X)

Cycles applied:
    Yearly      Q1: Jan-Mar | Q2: Apr-Jun | Q3: Jul-Sep | Q4: Oct-Dec
    Monthly     Q1-Q4 = Week 1..Week 4 of the month
    Weekly      Q1: Mon | Q2: Tue | Q3: Wed | Q4: Thu (Fri = end-of-week reaction)
    Daily       Q1: Asia | Q2: London | Q3: NY AM | Q4: NY PM
    90-min Micro inside each session quarter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

QUARTER_LABELS = {
    1: ("A", "Accumulation"),
    2: ("M", "Manipulation"),
    3: ("D", "Distribution"),
    4: ("X", "Continuation / Reversal"),
}


@dataclass
class QuarterInfo:
    cycle: str        # "Yearly" | "Monthly" | "Weekly" | "Daily" | "90min"
    q: int            # 1..4
    code: str         # A | M | D | X
    description: str


def _yearly_q(dt: datetime) -> int:
    return ((dt.month - 1) // 3) + 1


def _monthly_q(dt: datetime) -> int:
    # Map ISO day-of-month into 4 quarters of ~7-8 days.
    week = (dt.day - 1) // 7 + 1
    return min(week, 4)


def _weekly_q(dt: datetime) -> int:
    # Mon=1..Sun=7. Friday is treated as Q4 wrap.
    iso = dt.isoweekday()
    if iso >= 5:
        return 4
    return iso  # Mon=1 → Q1, Tue=2 → Q2, Wed=3 → Q3, Thu=4 → Q4


def _daily_q(dt: datetime) -> int:
    """Daily Q follows ICT session quarters, 6h each starting at 18:00 UTC.
        Q1 Asia    : 18:00 → 00:00
        Q2 London  : 00:00 → 06:00
        Q3 NY AM   : 06:00 → 12:00
        Q4 NY PM   : 12:00 → 18:00
    The original Alchemist material uses local-equivalent times — this UTC mapping
    keeps the cycle symmetrical and detectable from data.
    """
    hour = dt.astimezone(UTC).hour
    if hour >= 18 or hour < 0:
        return 1
    if hour < 6:
        return 2
    if hour < 12:
        return 3
    return 4


def _ninety_min_q(dt: datetime) -> int:
    """Inside a 6-hour session, quarters are 90 minutes long."""
    h = dt.astimezone(UTC).hour
    m = dt.astimezone(UTC).minute
    minutes_into_session = (h * 60 + m) % 360
    return min(minutes_into_session // 90 + 1, 4)


def current_quarters(now: datetime | None = None) -> list[QuarterInfo]:
    now = now or datetime.now(UTC)
    cycles = [
        ("Yearly", _yearly_q(now)),
        ("Monthly", _monthly_q(now)),
        ("Weekly", _weekly_q(now)),
        ("Daily", _daily_q(now)),
        ("90min", _ninety_min_q(now)),
    ]
    out: list[QuarterInfo] = []
    for name, q in cycles:
        code, desc = QUARTER_LABELS[q]
        out.append(QuarterInfo(cycle=name, q=q, code=code, description=desc))
    return out


def directional_bias(daily_q: int) -> str:
    """The AMD/X model implies a directional bias for the running quarter:
        Q1 → ranging / accumulating (no bias)
        Q2 → manipulation: fade the previous-quarter extreme
        Q3 → expansion: trend continuation
        Q4 → continuation OR reversal (decision quarter)
    """
    return {
        1: "RANGING (Accumulation)",
        2: "MANIPULATION (fade extremes)",
        3: "EXPANSION (trend continuation)",
        4: "DECISION (continuation or reversal)",
    }[daily_q]
