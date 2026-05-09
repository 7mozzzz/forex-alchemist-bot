"""Discord bot entrypoint — slash commands + scheduled daily signals."""
from __future__ import annotations

import asyncio
import io
import logging
from datetime import UTC, datetime, time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from ..charts import render_signal_chart
from ..config import Settings
from ..data.twelvedata import TwelveDataClient
from ..pipeline import analyse
from ..strategy.levels import find_key_levels
from ..strategy.news import fetch_high_impact_events
from ..strategy.sessions import asia_range, current_session
from ..strategy.signal import SignalContext, TradeSignal
from ..strategy.structure import analyze_structure
from . import embeds

logger = logging.getLogger(__name__)


# Session-open auto-scan times (UTC). Each fires at the opening minute of a major
# trading session: Asia (Tokyo) at 23:00, London at 07:00, New York at 12:00.
# Strict mode is used so only A+ score>=10, RR>=3, M5-confirmed setups are posted.
SESSION_OPEN_TIMES = [
    time(23, 0, tzinfo=UTC),  # Asia open  (Tokyo)
    time(7, 0, tzinfo=UTC),   # London open
    time(12, 0, tzinfo=UTC),  # New York open
]


class AlchemistBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = False  # only slash commands
        super().__init__(command_prefix="!", intents=intents)
        self.settings = settings
        self._client: TwelveDataClient | None = None

    async def setup_hook(self) -> None:
        self._client = await TwelveDataClient(self.settings.twelvedata_api_key).__aenter__()
        await self.tree.sync()
        self.session_scan.start()
        logger.info("Slash commands synced & session-open scheduler started (Asia 23:00, London 07:00, NY 12:00 UTC).")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
        await super().close()

    @property
    def td(self) -> TwelveDataClient:
        assert self._client is not None
        return self._client

    @tasks.loop(time=SESSION_OPEN_TIMES)
    async def session_scan(self) -> None:
        """Strict session-open scan: only A+ (score>=10), RR>=3, M5-confirmed,
        Q2/Q3-aligned, news-clear setups are published."""
        if not self.settings.signal_channel_ids:
            logger.info("session_scan: no SIGNAL_CHANNEL_IDS configured, skipping.")
            return
        sess = current_session()
        sess_name = sess.name if sess else "Session"
        logger.info("session_scan (%s) — strict scanning %s", sess_name, self.settings.watchlist)

        # Fetch the news calendar once for the whole batch.
        news_events = await fetch_high_impact_events()

        all_signals: list[tuple[SignalContext, TradeSignal]] = []
        for symbol in self.settings.watchlist:
            try:
                ctx, signals = await analyse(
                    self.td, symbol, strict=True, news_events=news_events
                )
                if signals:
                    all_signals.append((ctx, signals[0]))  # best per symbol
            except Exception:  # noqa: BLE001
                logger.exception("session_scan failed for %s", symbol)

        if not all_signals:
            logger.info("session_scan: no A+ setups passed strict filters this session.")
            return
        all_signals.sort(key=lambda r: r[1].score, reverse=True)

        for channel_id in self.settings.signal_channel_ids:
            channel = self.get_channel(channel_id) or await self.fetch_channel(channel_id)
            if channel is None or not isinstance(channel, discord.abc.Messageable):
                continue
            await channel.send(
                content=f"**{sess_name} Open — A+ Strict Setups**",
                embed=embeds.market_state_embed(),
            )
            for ctx, sig in all_signals:
                file = await _make_chart_file(ctx, sig)
                await channel.send(embed=embeds.signal_embed(sig), file=file)

    @session_scan.before_loop
    async def _before_scan(self) -> None:
        await self.wait_until_ready()


async def _make_chart_file(ctx, sig) -> discord.File:
    h1 = ctx.timeframes.get("H1")
    png = await asyncio.to_thread(render_signal_chart, h1, sig, "H1")
    return discord.File(io.BytesIO(png), filename=f"{sig.symbol.replace('/', '')}_{sig.side.value}.png")


def register_commands(bot: AlchemistBot) -> None:

    @bot.tree.command(name="help", description="Show command guide.")
    async def help_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=embeds.help_embed(), ephemeral=True)

    @bot.tree.command(name="about", description="Show the strategy stack used by the bot.")
    async def about_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=embeds.about_embed(), ephemeral=True)

    @bot.tree.command(name="sessions", description="Show ICT kill-zone status + Asia range.")
    async def sessions_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        sess = current_session()
        # Use XAUUSD H1 for asia range
        try:
            df = await bot.td.fetch_ohlc("XAU/USD", "H1", outputsize=120)
            ar = asia_range(df)
        except Exception:
            ar = None
        embed = embeds.market_state_embed()
        if ar:
            embed.add_field(
                name="Asia Range (XAU/USD)",
                value=f"High: **{ar.high:.2f}**\nLow:  **{ar.low:.2f}**",
                inline=False,
            )
        embed.set_field_at(0, name="Active Session",
                           value=f"**{sess.name}** {'🔥' if sess and sess.is_kill_zone else ''}" if sess else "—",
                           inline=False)
        await interaction.followup.send(embed=embed)

    @bot.tree.command(name="quarterly", description="Show current Daye Quarterly Theory state.")
    async def quarterly_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(embed=embeds.market_state_embed())

    @bot.tree.command(name="signal", description="Run multi-timeframe analysis on a symbol.")
    @app_commands.describe(symbol="Pair like XAU/USD, EUR/USD, GBP/USD, USD/JPY, AUD/USD")
    async def signal_cmd(interaction: discord.Interaction, symbol: str) -> None:
        await interaction.response.defer(thinking=True)
        symbol = symbol.upper().replace(" ", "")
        if "/" not in symbol and len(symbol) == 6:
            symbol = f"{symbol[:3]}/{symbol[3:]}"
        try:
            ctx, signals = await analyse(bot.td, symbol)
        except Exception as exc:  # noqa: BLE001
            await interaction.followup.send(
                embed=embeds.empty_signal_embed(symbol, f"Data error: {exc}")
            )
            return
        if not signals:
            await interaction.followup.send(
                embed=embeds.empty_signal_embed(symbol, "No fresh POI with inducement at the moment.")
            )
            return
        sig = signals[0]
        file = await _make_chart_file(ctx, sig)
        embed = embeds.signal_embed(sig)
        embed.set_image(url=f"attachment://{file.filename}")
        await interaction.followup.send(embed=embed, file=file)

    @bot.tree.command(name="scan", description="Scan the whole watchlist for A-grade setups.")
    async def scan_cmd(interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        results = []
        for symbol in bot.settings.watchlist:
            try:
                ctx, signals = await analyse(bot.td, symbol)
                if signals:
                    results.append((ctx, signals[0]))
            except Exception:  # noqa: BLE001
                logger.exception("scan failed for %s", symbol)
        if not results:
            await interaction.followup.send(content="No setups found right now.")
            return
        results.sort(key=lambda r: r[1].score, reverse=True)
        await interaction.followup.send(embed=embeds.market_state_embed())
        for ctx, sig in results[:5]:
            file = await _make_chart_file(ctx, sig)
            embed = embeds.signal_embed(sig)
            embed.set_image(url=f"attachment://{file.filename}")
            await interaction.followup.send(embed=embed, file=file)

    @bot.tree.command(name="levels", description="List the freshest MSNR key levels for a symbol.")
    @app_commands.describe(symbol="Pair like XAU/USD or EUR/USD")
    async def levels_cmd(interaction: discord.Interaction, symbol: str) -> None:
        await interaction.response.defer(thinking=True)
        symbol = symbol.upper().replace(" ", "")
        if "/" not in symbol and len(symbol) == 6:
            symbol = f"{symbol[:3]}/{symbol[3:]}"
        try:
            df_h1 = await bot.td.fetch_ohlc(symbol, "H1")
        except Exception as exc:  # noqa: BLE001
            await interaction.followup.send(
                embed=embeds.empty_signal_embed(symbol, f"Data error: {exc}")
            )
            return
        snap = analyze_structure(df_h1)
        levels = [lvl for lvl in find_key_levels(df_h1, snap.swings) if lvl.fresh]
        levels = levels[-12:]
        embed = discord.Embed(
            title=f"🗺️ {symbol} — Fresh MSNR Key Levels (H1)",
            color=embeds.COLOR_INFO,
        )
        if not levels:
            embed.description = "No fresh levels detected right now."
        else:
            buys = [f"`{lvl.price:>10.5f}`  {lvl.kind.value}" for lvl in levels if lvl.side == "BUY"]
            sells = [f"`{lvl.price:>10.5f}`  {lvl.kind.value}" for lvl in levels if lvl.side == "SELL"]
            if buys:
                embed.add_field(name="🟢 BUY POIs", value="\n".join(buys[-6:]), inline=True)
            if sells:
                embed.add_field(name="🔴 SELL POIs", value="\n".join(sells[-6:]), inline=True)
        embed.set_footer(text="Forex Alchemist  •  MSNR fresh-level scan")
        embed.timestamp = datetime.now(UTC)
        await interaction.followup.send(embed=embed)


async def _amain(settings: Settings) -> None:
    bot = AlchemistBot(settings)
    register_commands(bot)
    await bot.start(settings.discord_token)


def run() -> None:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    settings = Settings.load()
    logging.getLogger().setLevel(settings.log_level)
    asyncio.run(_amain(settings))


if __name__ == "__main__":
    run()
