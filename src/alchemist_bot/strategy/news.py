"""High-impact economic news filter using ForexFactory's free weekly XML feed.

Used in strict mode: a setup is rejected if there's a HIGH-impact event for any
of the involved currencies within +/- the configured window.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta, timezone

import aiohttp

logger = logging.getLogger(__name__)

FF_WEEKLY_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

# Currencies our watchlist exposes.
SYMBOL_CURRENCIES: dict[str, list[str]] = {
    "EUR/USD": ["EUR", "USD"],
    "GBP/USD": ["GBP", "USD"],
    "USD/JPY": ["USD", "JPY"],
    "AUD/USD": ["AUD", "USD"],
    "NZD/USD": ["NZD", "USD"],
    "USD/CHF": ["USD", "CHF"],
    "USD/CAD": ["USD", "CAD"],
    # Gold is USD-driven.
    "XAU/USD": ["USD"],
    "XAG/USD": ["USD"],
}


@dataclass(frozen=True)
class NewsEvent:
    when: datetime
    currency: str
    impact: str  # "High" / "Medium" / "Low"
    title: str


_FF_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(am|pm)?", re.IGNORECASE)


def _parse_ff_datetime(date_text: str, time_text: str) -> datetime | None:
    """ForexFactory dates look like '04-29-2026' and times '8:30am'/'All Day'/'Tentative'.

    The feed is published in EST (UTC-5, no DST in their data convention)."""
    if not date_text or not time_text:
        return None
    if time_text.lower().strip() in {"all day", "tentative"}:
        return None
    try:
        month, day, year = date_text.split("-")
        date_part = datetime(int(year), int(month), int(day))
    except Exception:  # noqa: BLE001
        return None
    m = _FF_TIME_RE.match(time_text.strip())
    if not m:
        return None
    hour = int(m.group(1)) % 12
    minute = int(m.group(2))
    suffix = (m.group(3) or "").lower()
    if suffix == "pm":
        hour += 12
    naive = date_part.replace(hour=hour, minute=minute)
    # ForexFactory feed publishes EST. Treat as UTC-5 fixed offset.
    return naive.replace(tzinfo=timezone(timedelta(hours=-5))).astimezone(UTC)


async def fetch_high_impact_events(
    session: aiohttp.ClientSession | None = None,
) -> list[NewsEvent]:
    """Download this-week's high-impact events from ForexFactory."""
    own = session is None
    sess = session or aiohttp.ClientSession()
    try:
        async with sess.get(FF_WEEKLY_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            text = await resp.text()
    except Exception:  # noqa: BLE001
        logger.exception("Failed to fetch ForexFactory news feed")
        return []
    finally:
        if own:
            await sess.close()

    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        logger.exception("Failed to parse ForexFactory XML")
        return []

    out: list[NewsEvent] = []
    for ev in root.findall(".//event"):
        impact = (ev.findtext("impact") or "").strip()
        if impact.lower() != "high":
            continue
        title = (ev.findtext("title") or "").strip()
        currency = (ev.findtext("country") or "").strip().upper()
        date_text = (ev.findtext("date") or "").strip()
        time_text = (ev.findtext("time") or "").strip()
        when = _parse_ff_datetime(date_text, time_text)
        if when is None:
            continue
        out.append(NewsEvent(when=when, currency=currency, impact=impact, title=title))
    return out


def is_news_clear(
    events: list[NewsEvent],
    symbol: str,
    now: datetime | None = None,
    window_minutes: int = 30,
) -> tuple[bool, NewsEvent | None]:
    """Return (clear, blocking_event). Blocked if a HIGH event is within +/- window
    for any currency in the symbol."""
    now = now or datetime.now(UTC)
    currencies = set(SYMBOL_CURRENCIES.get(symbol.upper(), []))
    if not currencies:
        return True, None
    window = timedelta(minutes=window_minutes)
    for ev in events:
        if ev.currency not in currencies:
            continue
        if abs((ev.when - now).total_seconds()) <= window.total_seconds():
            return False, ev
    return True, None


def next_news_for(
    events: list[NewsEvent],
    symbol: str,
    now: datetime | None = None,
) -> NewsEvent | None:
    """Return the next upcoming high-impact event for the symbol's currencies, or None."""
    now = now or datetime.now(UTC)
    currencies = set(SYMBOL_CURRENCIES.get(symbol.upper(), []))
    upcoming = [e for e in events if e.currency in currencies and e.when >= now]
    upcoming.sort(key=lambda e: e.when)
    return upcoming[0] if upcoming else None


__all__ = [
    "NewsEvent",
    "fetch_high_impact_events",
    "is_news_clear",
    "next_news_for",
    "SYMBOL_CURRENCIES",
]


# Convenience exports for tests / sessions.
SESSION_OPENS_UTC = (time(23, 0), time(7, 0), time(12, 0))
