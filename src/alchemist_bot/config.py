"""Application configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    discord_token: str
    twelvedata_api_key: str
    signal_channel_ids: list[int] = field(default_factory=list)
    watchlist: list[str] = field(default_factory=list)
    timezone: str = "UTC"
    log_level: str = "INFO"
    cache_dir: Path = field(default_factory=lambda: Path("/tmp/alchemist_cache"))

    @classmethod
    def load(cls) -> Settings:
        token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
        td_key = os.environ.get("TWELVEDATA_API_KEY", "").strip()
        if not token:
            raise RuntimeError("DISCORD_BOT_TOKEN is missing — see .env.example")
        if not td_key:
            raise RuntimeError("TWELVEDATA_API_KEY is missing — see .env.example")

        watchlist = _split_csv(os.environ.get("WATCHLIST")) or [
            "XAU/USD",
            "EUR/USD",
            "GBP/USD",
            "USD/JPY",
            "AUD/USD",
        ]
        channels = [int(c) for c in _split_csv(os.environ.get("SIGNAL_CHANNEL_IDS"))]
        cache_dir = Path(os.environ.get("CACHE_DIR", "/tmp/alchemist_cache"))
        cache_dir.mkdir(parents=True, exist_ok=True)

        return cls(
            discord_token=token,
            twelvedata_api_key=td_key,
            signal_channel_ids=channels,
            watchlist=watchlist,
            timezone=os.environ.get("TIMEZONE", "UTC"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
            cache_dir=cache_dir,
        )
