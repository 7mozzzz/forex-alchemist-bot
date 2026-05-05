"""Rich Discord embeds — premium look & feel."""
from __future__ import annotations

from datetime import UTC, datetime

import discord

from ..strategy.quarterly import current_quarters
from ..strategy.sessions import current_session
from ..strategy.signal import SignalQuality, SignalSide, TradeSignal

# Premium colour palette
COLOR_BUY = 0x22C55E
COLOR_SELL = 0xEF4444
COLOR_NEUTRAL = 0xF5B342
COLOR_DARK = 0x0B0F1A
COLOR_INFO = 0x4F8DFD

QUALITY_EMOJI = {
    SignalQuality.A_PLUS: "🏆",
    SignalQuality.A: "⭐",
    SignalQuality.B: "✦",
    SignalQuality.C: "·",
}
SIDE_EMOJI = {
    SignalSide.BUY: "🟢",
    SignalSide.SELL: "🔴",
}


def _footer(embed: discord.Embed) -> None:
    embed.set_footer(text="Forex Alchemist  •  MSNR + SMC + LIT + ICT + QT + SMT")
    embed.timestamp = datetime.now(UTC)


def signal_embed(signal: TradeSignal) -> discord.Embed:
    color = COLOR_BUY if signal.side is SignalSide.BUY else COLOR_SELL
    title = (
        f"{SIDE_EMOJI[signal.side]} {signal.symbol}  •  "
        f"{signal.side.value}  •  {QUALITY_EMOJI[signal.quality]} {signal.quality.value}"
    )
    embed = discord.Embed(title=title, color=color, description=signal.notes or "")

    embed.add_field(
        name="📍 Entry / Risk",
        value=(
            f"```yaml\n"
            f"Entry : {signal.entry}\n"
            f"Stop  : {signal.stop_loss}\n"
            f"Score : {signal.score} / 12\n"
            f"```"
        ),
        inline=True,
    )
    embed.add_field(
        name="🎯 Targets",
        value=(
            f"```yaml\n"
            f"TP1 : {signal.tp1}  ({signal.rr1}R)\n"
            f"TP2 : {signal.tp2}  ({signal.rr2}R)\n"
            f"TP3 : {signal.tp3}  ({signal.rr3}R)\n"
            f"```"
        ),
        inline=True,
    )
    embed.add_field(
        name="🧭 Bias",
        value=f"HTF Trend: **{signal.htf_trend.value}**\nPOI: **{signal.poi.kind.value}** (fresh)",
        inline=False,
    )

    if signal.confluences:
        embed.add_field(
            name="🔬 Confluences",
            value="\n".join(f"• {c}" for c in signal.confluences[:8]),
            inline=False,
        )

    _footer(embed)
    return embed


def empty_signal_embed(symbol: str, reason: str) -> discord.Embed:
    embed = discord.Embed(
        title=f"{symbol}  •  No A-grade setup right now",
        description=reason,
        color=COLOR_NEUTRAL,
    )
    _footer(embed)
    return embed


def market_state_embed() -> discord.Embed:
    sess = current_session()
    qts = current_quarters()
    embed = discord.Embed(
        title="🌐 Market State",
        color=COLOR_INFO,
        description="ICT session + Daye Quarterly Theory snapshot.",
    )
    sess_text = f"**{sess.name}**" if sess else "_No active kill zone_"
    if sess and sess.is_kill_zone:
        sess_text += "  🔥"
    embed.add_field(name="Session", value=sess_text, inline=False)
    qt_lines = []
    for q in qts:
        qt_lines.append(f"`{q.cycle:<8}`  Q{q.q}  **{q.code}** — {q.description}")
    embed.add_field(name="Quarterly Theory", value="\n".join(qt_lines), inline=False)
    _footer(embed)
    return embed


def help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🪙 Forex Alchemist — Command Guide",
        description=(
            "A Discord bot that fuses **MSNR Key Levels**, **SMC + LIT**, "
            "**ICT Kill Zones**, **Daye Quarterly Theory**, and **SMT divergence** "
            "to surface A-grade Forex / Gold setups.\n\n"
            "🔔 **Auto-scan** runs at every session open (Asia 23:00, London 07:00, "
            "NY 12:00 UTC) in **strict mode**: only A+ score ≥ 10/12, RR ≥ 3, "
            "M5 confirmed, Q2/Q3 aligned, news-clear setups are posted."
        ),
        color=COLOR_INFO,
    )
    embed.add_field(
        name="`/signal <symbol>`",
        value="On-demand multi-timeframe analysis with annotated chart.",
        inline=False,
    )
    embed.add_field(
        name="`/scan`",
        value="Scan the whole watchlist (XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD).",
        inline=False,
    )
    embed.add_field(
        name="`/levels <symbol>`",
        value="List the freshest MSNR key levels (Support / Resistance / SBR / RBS / QML / OCL).",
        inline=False,
    )
    embed.add_field(
        name="`/quarterly`",
        value="Show current Quarterly Theory state (Yearly / Monthly / Weekly / Daily / 90-min).",
        inline=False,
    )
    embed.add_field(
        name="`/sessions`",
        value="Show ICT kill-zone status + Asia range high / low.",
        inline=False,
    )
    embed.add_field(
        name="`/about`",
        value="Strategy summary and credits.",
        inline=False,
    )
    _footer(embed)
    return embed


def about_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🪙 Forex Alchemist — Strategy Stack",
        color=COLOR_INFO,
        description=(
            "**Strict A+ filter** is active on the auto-scan. Each session-open\n"
            "signal must satisfy *all* of the following — anything weaker is dropped:\n"
            "• Confluence score **≥ 10/12** (A+ grade)\n"
            "• Risk:Reward at TP1 **≥ 3.0**\n"
            "• M5 BOS or sweep within last 5 bars\n"
            "• Daily Quarterly = **Q2** (manipulation) or **Q3** (distribution), aligned\n"
            "• No high-impact news within ±30 minutes\n"
            "• Inducement (LIT) confirmed before the POI\n\n"
            "Every signal is a confluence of:\n"
            "• **MSNR Key Levels** — Support / Resistance / SBR / RBS / QML / OCL\n"
            "• **SMC + LIT** — BOS, CHOCH, Inducement (every POI must have IDM)\n"
            "• **ICT Kill Zones** — Asia range, London, NY AM/PM\n"
            "• **Daye Quarterly Theory** — A·M·D·X cycles (Yearly → Micro)\n"
            "• **SMT divergence** — correlated-pair confirmation\n"
            "• **PSP** — Precision swing point on LTF\n\n"
            "Risk rule: **single-price entry, 1 layer per setup, 1–5% risk**.\n"
            "Trade only when ≥ 7/12 score and HTF trend agrees."
        ),
    )
    _footer(embed)
    return embed
