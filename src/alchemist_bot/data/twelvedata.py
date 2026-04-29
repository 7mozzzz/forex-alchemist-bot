"""TwelveData REST client for Forex and Gold OHLC data."""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass

import aiohttp
import pandas as pd

logger = logging.getLogger(__name__)

BASE_URL = "https://api.twelvedata.com"

# TwelveData supports these intervals natively.
SUPPORTED_INTERVALS = {
    "1min", "5min", "15min", "30min", "45min",
    "1h", "2h", "4h", "8h",
    "1day", "1week", "1month",
}

# Map a friendly timeframe name → (TwelveData interval, default outputsize)
TIMEFRAMES = {
    "M1": ("1min", 500),
    "M5": ("5min", 500),
    "M15": ("15min", 500),
    "M30": ("30min", 500),
    "H1": ("1h", 500),
    "H4": ("4h", 500),
    "D1": ("1day", 500),
    "W1": ("1week", 200),
    "MN": ("1month", 100),
}


@dataclass
class Quote:
    symbol: str
    price: float
    bid: float | None
    ask: float | None
    timestamp: pd.Timestamp


class TwelveDataClient:
    """Lightweight async client for the TwelveData public REST API."""

    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession | None = None,
        max_per_minute: int = 7,
    ) -> None:
        self.api_key = api_key
        self._session = session
        self._owns_session = session is None
        # Free tier: 8 req/min — token-bucket-style rate limiter, slightly under the limit.
        self._max_per_minute = max_per_minute
        self._calls: deque[float] = deque()
        self._rate_lock = asyncio.Lock()

    async def __aenter__(self) -> TwelveDataClient:
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def _wait_for_slot(self) -> None:
        """Block until we have a free request slot inside the rolling 60s window."""
        async with self._rate_lock:
            now = time.monotonic()
            while self._calls and now - self._calls[0] >= 60:
                self._calls.popleft()
            if len(self._calls) >= self._max_per_minute:
                wait = 60 - (now - self._calls[0]) + 0.05
                logger.info("TwelveData rate-limit: sleeping %.1fs", wait)
                await asyncio.sleep(wait)
                now = time.monotonic()
                while self._calls and now - self._calls[0] >= 60:
                    self._calls.popleft()
            self._calls.append(now)

    async def _get(self, endpoint: str, params: dict) -> dict:
        assert self._session is not None, "TwelveDataClient must be used as a context manager"
        params = {**params, "apikey": self.api_key}
        url = f"{BASE_URL}/{endpoint}"
        await self._wait_for_slot()
        timeout = aiohttp.ClientTimeout(total=30)
        async with self._session.get(url, params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            payload = await resp.json()
        if isinstance(payload, dict) and payload.get("status") == "error":
            raise RuntimeError(f"TwelveData error: {payload.get('message', payload)}")
        return payload

    async def fetch_ohlc(
        self,
        symbol: str,
        timeframe: str,
        outputsize: int | None = None,
    ) -> pd.DataFrame:
        """Fetch OHLC candles. Returns a DataFrame indexed by UTC datetime ascending."""
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        interval, default_size = TIMEFRAMES[timeframe]
        size = outputsize or default_size

        data = await self._get(
            "time_series",
            {
                "symbol": symbol,
                "interval": interval,
                "outputsize": size,
                "format": "JSON",
                "timezone": "UTC",
            },
        )
        values = data.get("values")
        if not values:
            raise RuntimeError(f"No OHLC data returned for {symbol} {timeframe}")

        df = pd.DataFrame(values)
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        for col in ("open", "high", "low", "close"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce")
        else:
            df["volume"] = 0.0
        df = df.sort_values("datetime").reset_index(drop=True)
        df = df.set_index("datetime")
        return df[["open", "high", "low", "close", "volume"]]

    async def fetch_quote(self, symbol: str) -> Quote:
        data = await self._get("quote", {"symbol": symbol})
        ts = pd.Timestamp(int(data.get("timestamp", 0)), unit="s", tz="UTC")
        return Quote(
            symbol=symbol,
            price=float(data["close"]),
            bid=float(data["bid"]) if data.get("bid") else None,
            ask=float(data["ask"]) if data.get("ask") else None,
            timestamp=ts,
        )

    async def fetch_multi_timeframe(
        self,
        symbol: str,
        timeframes: list[str],
    ) -> dict[str, pd.DataFrame]:
        """Fetch multiple timeframes for the same symbol concurrently."""
        results = await asyncio.gather(
            *(self.fetch_ohlc(symbol, tf) for tf in timeframes),
            return_exceptions=True,
        )
        out: dict[str, pd.DataFrame] = {}
        for tf, res in zip(timeframes, results, strict=False):
            if isinstance(res, Exception):
                logger.warning("Failed to fetch %s %s: %s", symbol, tf, res)
                continue
            out[tf] = res
        return out
