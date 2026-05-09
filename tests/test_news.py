"""News blackout filter tests."""
from datetime import UTC, datetime, timedelta

from alchemist_bot.strategy.news import (
    NewsEvent,
    is_news_clear,
    next_news_for,
)


def _evt(when: datetime, currency: str, title: str = "Test") -> NewsEvent:
    return NewsEvent(when=when, currency=currency, impact="High", title=title)


def test_is_news_clear_returns_true_when_no_currency_match():
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    events = [_evt(now, "JPY")]
    clear, blocking = is_news_clear(events, "EUR/USD", now=now)
    assert clear is True
    assert blocking is None


def test_is_news_clear_blocks_within_window():
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    events = [_evt(now + timedelta(minutes=15), "USD", "NFP")]
    clear, blocking = is_news_clear(events, "EUR/USD", now=now, window_minutes=30)
    assert clear is False
    assert blocking is not None
    assert blocking.title == "NFP"


def test_is_news_clear_passes_outside_window():
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    events = [_evt(now + timedelta(minutes=45), "USD", "FOMC")]
    clear, _ = is_news_clear(events, "EUR/USD", now=now, window_minutes=30)
    assert clear is True


def test_next_news_for_returns_soonest_upcoming():
    now = datetime(2026, 4, 29, 12, 0, tzinfo=UTC)
    events = [
        _evt(now + timedelta(hours=2), "USD", "CPI"),
        _evt(now + timedelta(hours=1), "USD", "PMI"),
        _evt(now - timedelta(hours=1), "USD", "Past"),
    ]
    nxt = next_news_for(events, "XAU/USD", now=now)
    assert nxt is not None
    assert nxt.title == "PMI"
