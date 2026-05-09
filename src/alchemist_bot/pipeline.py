"""High-level pipeline that turns a symbol into trade signals + chart bytes."""
from __future__ import annotations

import asyncio
import logging

import pandas as pd

from .data.twelvedata import TwelveDataClient
from .strategy.news import NewsEvent, fetch_high_impact_events
from .strategy.signal import SignalContext, TradeSignal, build_signals
from .strategy.smt import SMT_CORRELATIONS

logger = logging.getLogger(__name__)

# Standard analysis stack (also used by /signal).
DEFAULT_TIMEFRAMES = ["H4", "H1", "M15"]
# Strict-mode (session-open auto-scan) requires the M5 LTF for confirmation.
STRICT_TIMEFRAMES = ["H4", "H1", "M15", "M5"]


async def analyse(
    client: TwelveDataClient,
    symbol: str,
    timeframes: list[str] | None = None,
    *,
    strict: bool = False,
    news_events: list[NewsEvent] | None = None,
) -> tuple[SignalContext, list[TradeSignal]]:
    """Fetch all timeframes + correlated peers, then build signals.

    When ``strict=True`` the call uses the wider STRICT_TIMEFRAMES stack and the
    high-impact news blackout, returning only A+ session-open setups with RR>=3.
    """
    if timeframes is None:
        timeframes = STRICT_TIMEFRAMES if strict else DEFAULT_TIMEFRAMES
    tf_data = await client.fetch_multi_timeframe(symbol, timeframes)

    peer_symbols = [peer for peer, _ in SMT_CORRELATIONS.get(symbol, [])]
    peer_data: dict[str, pd.DataFrame] = {}
    if peer_symbols:
        peer_results = await asyncio.gather(
            *(client.fetch_ohlc(p, "H1") for p in peer_symbols),
            return_exceptions=True,
        )
        for peer, res in zip(peer_symbols, peer_results, strict=False):
            if isinstance(res, Exception):
                logger.debug("SMT peer fetch failed for %s: %s", peer, res)
                continue
            peer_data[peer] = res

    events = news_events if news_events is not None else (
        await fetch_high_impact_events() if strict else []
    )

    ctx = SignalContext(
        symbol=symbol,
        timeframes=tf_data,
        peer_dfs=peer_data,
        news_events=events,
    )
    signals = build_signals(ctx, strict=strict)
    signals.sort(key=lambda s: s.score, reverse=True)
    return ctx, signals
