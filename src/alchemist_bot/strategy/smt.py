"""SMT Divergence detection between correlated pairs.

If a positively-correlated pair makes a higher high while its peer makes a lower
high (or vice-versa), that's a Sequential SMT divergence — a tell that the move
lacks institutional confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# Correlations used by the bot. Each tuple = (primary, peer, sign).
# sign = +1 means assets normally move together; -1 = inverse.
SMT_CORRELATIONS: dict[str, list[tuple[str, int]]] = {
    "EUR/USD": [("GBP/USD", +1), ("AUD/USD", +1)],
    "GBP/USD": [("EUR/USD", +1), ("AUD/USD", +1)],
    "AUD/USD": [("NZD/USD", +1), ("EUR/USD", +1)],
    "USD/JPY": [("USD/CHF", +1)],
    # XAG/USD requires a paid TwelveData plan. We fall back to USD/CHF as an
    # inverse-USD strength proxy when correlating gold.
    "XAU/USD": [("USD/CHF", -1)],
}


@dataclass
class SMTSignal:
    primary: str
    peer: str
    direction: str  # "BULLISH" | "BEARISH"
    description: str


def _last_two_swings(df: pd.DataFrame, lookback: int = 30) -> tuple[float, float, float, float]:
    """Return (last_high, prev_high, last_low, prev_low) over the last `lookback` bars."""
    sub = df.iloc[-lookback:]
    highs = sub["high"]
    lows = sub["low"]
    sorted_h = highs.sort_values(ascending=False)
    sorted_l = lows.sort_values()
    last_high = float(sorted_h.iloc[0])
    prev_high = float(sorted_h.iloc[1]) if len(sorted_h) > 1 else last_high
    last_low = float(sorted_l.iloc[0])
    prev_low = float(sorted_l.iloc[1]) if len(sorted_l) > 1 else last_low
    return last_high, prev_high, last_low, prev_low


def detect_smt(
    primary: str,
    primary_df: pd.DataFrame,
    peers: dict[str, pd.DataFrame],
    lookback: int = 30,
) -> list[SMTSignal]:
    """Compare last swing-highs and lows of the primary against each peer to flag SMT."""
    if primary_df.empty or primary not in SMT_CORRELATIONS:
        return []

    p_lh, p_ph, p_ll, p_pl = _last_two_swings(primary_df, lookback)
    p_higher_high = p_lh > p_ph
    p_lower_low = p_ll < p_pl

    signals: list[SMTSignal] = []
    for peer, sign in SMT_CORRELATIONS[primary]:
        df = peers.get(peer)
        if df is None or df.empty:
            continue
        q_lh, q_ph, q_ll, q_pl = _last_two_swings(df, lookback)
        q_higher_high = q_lh > q_ph
        q_lower_low = q_ll < q_pl
        # Apply sign for inverse correlations.
        if sign == -1:
            q_higher_high, q_lower_low = q_lower_low, q_higher_high

        if p_higher_high and not q_higher_high:
            signals.append(
                SMTSignal(
                    primary=primary,
                    peer=peer,
                    direction="BEARISH",
                    description=f"{primary} made a higher high, {peer} did not — bearish SMT.",
                )
            )
        if p_lower_low and not q_lower_low:
            signals.append(
                SMTSignal(
                    primary=primary,
                    peer=peer,
                    direction="BULLISH",
                    description=f"{primary} made a lower low, {peer} did not — bullish SMT.",
                )
            )
    return signals
