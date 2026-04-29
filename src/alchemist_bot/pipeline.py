"""High-level pipeline that turns a symbol into trade signals + chart bytes."""
from __future__ import annotations

import asyncio
import logging

import pandas as pd

from .data.twelvedata import TwelveDataClient
from .strategy.signal import SignalContext, TradeSignal, build_signals
from .strategy.smt import SMT_CORRELATIONS

logger = logging.getLogger(__name__)

DEFAULT_TIMEFRAMES = ["H4", "H1", "M15"]


async def analyse(
    client: TwelveDataClient,
    symbol: str,
    timeframes: list[str] | None = None,
) -> tuple[SignalContext, list[TradeSignal]]:
    """Fetch all timeframes + correlated peers, then build signals."""
    timeframes = timeframes or DEFAULT_TIMEFRAMES
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

    ctx = SignalContext(symbol=symbol, timeframes=tf_data, peer_dfs=peer_data)
    signals = build_signals(ctx)
    signals.sort(key=lambda s: s.score, reverse=True)
    return ctx, signals
