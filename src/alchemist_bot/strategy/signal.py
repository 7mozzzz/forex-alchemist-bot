"""Signal aggregator — fuses MSNR + SMC + LIT + ICT + QT + SMT into trade setups.

Trade-construction rules (from the Alchemist + iscTrader + S.Fx materials):

    1. HTF context first (D1 → H4)         : trend + dominant direction
    2. Locate FRESH MSNR key levels in the direction of the HTF trend
    3. Inducement (LIT) must be present between current price and the POI
    4. Confirm with at least one of: PSP candle, sweep + close-back, BOS/CHOCH on LTF
    5. Quarterly Theory bias must agree (don't sell in Q4 if Q3 just expanded down etc.)
    6. SMT divergence boosts the score when present
    7. Single price entry (Alchemist rule: no zones), tight SL beyond the level
    8. TP1 = nearest opposite key level, TP2 = next opposite, TP3 = HTF objective
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

import pandas as pd

from . import levels as level_mod
from . import liquidity as liq_mod
from . import news as news_mod
from . import quarterly as qt_mod
from . import smt as smt_mod
from . import structure as struct_mod
from .levels import KeyLevel, LevelKind
from .news import NewsEvent
from .sessions import asia_range, current_session
from .structure import Trend, atr

# Strict-mode thresholds (used by the daily session-open auto-scan).
# Calibrated to produce ~1-3 high-quality setups per session-open day instead
# of zero. Hard gates: IDM + M5 confirm + news-clear. QT alignment is a bonus.
STRICT_MIN_SCORE: int = 8
STRICT_MIN_RR1: float = 2.0
STRICT_LTF_LOOKBACK: int = 5  # bars on M5
NEWS_BLACKOUT_MINUTES: int = 30


class SignalSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class SignalQuality(StrEnum):
    A_PLUS = "A+"
    A = "A"
    B = "B"
    C = "C"


@dataclass
class TradeSignal:
    symbol: str
    side: SignalSide
    quality: SignalQuality
    score: int
    entry: float
    stop_loss: float
    tp1: float
    tp2: float
    tp3: float
    rr1: float
    rr2: float
    rr3: float
    poi: KeyLevel
    htf_trend: Trend
    confluences: list[str] = field(default_factory=list)
    notes: str = ""
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "quality": self.quality.value,
            "score": self.score,
            "entry": self.entry,
            "stop_loss": self.stop_loss,
            "tp1": self.tp1,
            "tp2": self.tp2,
            "tp3": self.tp3,
            "rr1": self.rr1,
            "rr2": self.rr2,
            "rr3": self.rr3,
            "poi": self.poi.as_dict(),
            "htf_trend": self.htf_trend.value,
            "confluences": self.confluences,
            "notes": self.notes,
            "generated_at": self.generated_at.isoformat(),
        }


def _quality_from_score(score: int) -> SignalQuality:
    if score >= 10:
        return SignalQuality.A_PLUS
    if score >= 8:
        return SignalQuality.A
    if score >= 6:
        return SignalQuality.B
    return SignalQuality.C


def _atr_buffer(price: float, atr_value: float) -> float:
    """SL buffer = max(0.2 * ATR, 0.05% of price). Tight by design (Alchemist single-entry)."""
    return max(0.2 * atr_value, abs(price) * 0.0005)


def _round(value: float, symbol: str) -> float:
    """Round the price to a sensible number of decimals based on the symbol class."""
    if "JPY" in symbol:
        return round(value, 3)
    if "XAU" in symbol or "XAG" in symbol:
        return round(value, 2)
    return round(value, 5)


@dataclass
class SignalContext:
    """Container holding everything fetched/computed for a single symbol."""
    symbol: str
    timeframes: dict[str, pd.DataFrame]
    peer_dfs: dict[str, pd.DataFrame] = field(default_factory=dict)
    news_events: list[NewsEvent] = field(default_factory=list)


def build_signals(ctx: SignalContext, *, strict: bool = False) -> list[TradeSignal]:
    """Run the full pipeline and return zero or more trade setups for `ctx.symbol`.

    When ``strict=True`` (used by the session-open auto-scan):
        * only setups with score >= STRICT_MIN_SCORE are returned
        * RR1 must be >= STRICT_MIN_RR1
        * the M5 timeframe must show a BOS or sweep in the matching direction
          within the last STRICT_LTF_LOOKBACK bars
        * inducement (LIT) must be confirmed
        * no high-impact news for the symbol's currencies inside +/-30 minutes
        * Quarterly Theory alignment is awarded as a score bonus, not a hard gate.
    """
    out: list[TradeSignal] = []
    h4 = ctx.timeframes.get("H4")
    h1 = ctx.timeframes.get("H1")
    m15 = ctx.timeframes.get("M15")
    m5 = ctx.timeframes.get("M5")
    if h4 is None or h1 is None or m15 is None or h4.empty or h1.empty or m15.empty:
        return out
    if strict and (m5 is None or m5.empty):
        return out

    # News blackout (strict mode only, applied per signal once we have a side).
    news_clear, news_block = (True, None)
    if strict:
        news_clear, news_block = news_mod.is_news_clear(
            ctx.news_events, ctx.symbol, window_minutes=NEWS_BLACKOUT_MINUTES
        )
        if not news_clear:
            return out  # Whole symbol is blacked out.

    # ---- HTF context
    h4_struct = struct_mod.analyze_structure(h4)
    h1_struct = struct_mod.analyze_structure(h1)
    m15_struct = struct_mod.analyze_structure(m15)

    htf_trend = h4_struct.trend
    if htf_trend is Trend.RANGING:
        htf_trend = h1_struct.trend  # fallback to H1

    # ---- POIs (combine H4 + H1 fresh levels)
    h4_levels = level_mod.find_key_levels(h4, h4_struct.swings)
    h1_levels = level_mod.find_key_levels(h1, h1_struct.swings)
    all_levels = h4_levels + h1_levels

    last_close = float(h1["close"].iloc[-1])
    h1_atr = atr(h1)

    # ---- Quarterly Theory bias
    qts = qt_mod.current_quarters()
    daily_q = next(q for q in qts if q.cycle == "Daily")
    qt_bias = qt_mod.directional_bias(daily_q.q)

    # ---- Liquidity sweeps + SMT
    h1_sweeps = liq_mod.detect_sweeps(h1, h1_struct.swings)
    smt_signals = smt_mod.detect_smt(ctx.symbol, h1, ctx.peer_dfs)

    # ---- Asia range (current day)
    a_range = asia_range(h1)
    sess = current_session()

    sides: list[SignalSide] = []
    if htf_trend is Trend.BULLISH:
        sides.append(SignalSide.BUY)
    elif htf_trend is Trend.BEARISH:
        sides.append(SignalSide.SELL)
    else:
        sides.extend([SignalSide.BUY, SignalSide.SELL])

    for side in sides:
        target_side = "BUY" if side is SignalSide.BUY else "SELL"
        nearest = level_mod.nearest_levels(all_levels, last_close, target_side, fresh_only=True, n=1)
        if not nearest:
            continue
        poi = nearest[0]

        # Inducement check — first try the LTF (M15), then HTF (H1) swings.
        idm_ok = liq_mod.has_inducement(
            m15_struct.swings,
            poi.created_at,
            target_side,
            poi_price=poi.price,
            current_price=last_close,
        ) or liq_mod.has_inducement(
            h1_struct.swings,
            poi.created_at,
            target_side,
            poi_price=poi.price,
            current_price=last_close,
        )

        # Build SL/TP
        buffer = _atr_buffer(last_close, h1_atr)
        if side is SignalSide.BUY:
            entry = poi.price
            sl = entry - buffer
            tp_pool = [lvl for lvl in all_levels if lvl.side == "SELL" and lvl.fresh and lvl.price > entry]
            tp_pool.sort(key=lambda lvl: lvl.price)
        else:
            entry = poi.price
            sl = entry + buffer
            tp_pool = [lvl for lvl in all_levels if lvl.side == "BUY" and lvl.fresh and lvl.price < entry]
            tp_pool.sort(key=lambda lvl: lvl.price, reverse=True)

        if len(tp_pool) < 1:
            continue

        # TP1, TP2, TP3 — fall back to ATR-based extensions if not enough fresh levels
        tp1 = tp_pool[0].price
        tp2 = tp_pool[1].price if len(tp_pool) > 1 else (
            tp1 + (1 if side is SignalSide.BUY else -1) * 1.0 * h1_atr
        )
        tp3 = tp_pool[2].price if len(tp_pool) > 2 else (
            tp1 + (1 if side is SignalSide.BUY else -1) * 2.5 * h1_atr
        )

        risk = abs(entry - sl)
        if risk <= 0:
            continue
        rr1 = abs(tp1 - entry) / risk
        rr2 = abs(tp2 - entry) / risk
        rr3 = abs(tp3 - entry) / risk
        min_rr = STRICT_MIN_RR1 if strict else 1.5
        if rr1 < min_rr:
            continue  # Alchemist: minimum RR rule

        # ---- Score
        confluences: list[str] = [
            f"HTF trend = {htf_trend.value}",
            f"POI = {poi.kind.value} @ {entry:.5f} (fresh)",
            f"Quarterly Theory: {daily_q.cycle} {daily_q.code} — {qt_bias}",
        ]
        score = 4
        if idm_ok:
            score += 2
            confluences.insert(2, "Inducement (IDM) confirmed — LIT trap present")
        else:
            confluences.insert(2, "No inducement yet — needs LTF sweep before entry")

        if poi.kind in (LevelKind.QML_BUY, LevelKind.QML_SELL):
            score += 1
            confluences.append("Quasimodo (QML) reversal level")
        if poi.kind in (LevelKind.SBR, LevelKind.RBS):
            score += 1
            confluences.append("Breaker structure (SBR/RBS)")

        # Liquidity sweep alignment
        relevant_sweep_dir = "SELLSIDE" if side is SignalSide.BUY else "BUYSIDE"
        if any(s.direction == relevant_sweep_dir for s in h1_sweeps[-5:]):
            score += 1
            confluences.append("Recent liquidity sweep aligns with setup")

        # Asia range alignment
        if a_range is not None:
            if side is SignalSide.BUY and last_close < a_range.low * 1.001:
                score += 1
                confluences.append(f"Below Asia low ({a_range.low:.5f}) — sellside liquidity grab")
            if side is SignalSide.SELL and last_close > a_range.high * 0.999:
                score += 1
                confluences.append(f"Above Asia high ({a_range.high:.5f}) — buyside liquidity grab")

        # Kill zone alignment
        if sess and sess.is_kill_zone:
            score += 1
            confluences.append(f"Inside {sess.name} kill zone")

        # SMT
        smt_aligned = [s for s in smt_signals if (
            (side is SignalSide.BUY and s.direction == "BULLISH")
            or (side is SignalSide.SELL and s.direction == "BEARISH")
        )]
        if smt_aligned:
            score += 1
            confluences.append(f"SMT divergence: {smt_aligned[0].description}")

        # M15 confirmation: BOS/CHOCH agreeing with side
        wants = "BULLISH" if side is SignalSide.BUY else "BEARISH"
        if m15_struct.events:
            last_event = m15_struct.events[-1]
            if last_event.direction == wants:
                score += 1
                confluences.append(f"M15 {last_event.kind} {last_event.direction} confirmation")

        # ---- LTF (M5) confirmation: BOS or sweep in the last N bars matching side.
        m5_confirmed = False
        if m5 is not None and not m5.empty:
            m5_struct = struct_mod.analyze_structure(m5)
            recent_events = m5_struct.events[-STRICT_LTF_LOOKBACK:]
            for ev in recent_events:
                if ev.direction == wants:
                    m5_confirmed = True
                    break
            m5_sweeps = liq_mod.detect_sweeps(m5, m5_struct.swings)
            sweep_dir = "SELLSIDE" if side is SignalSide.BUY else "BUYSIDE"
            if any(s.direction == sweep_dir for s in m5_sweeps[-STRICT_LTF_LOOKBACK:]):
                m5_confirmed = True
            if m5_confirmed:
                score += 1
                confluences.append(
                    f"M5 LTF confirmation ({wants.lower()} BOS or sweep in last {STRICT_LTF_LOOKBACK} bars)"
                )

        # ---- QT alignment: only count when Q2/Q3 matches the trade side.
        qt_aligned = False
        if daily_q.q == "Q2":
            # Q2 = manipulation: a sweep against trend that traps shorts/longs.
            qt_aligned = (
                (side is SignalSide.BUY and "BULLISH" in qt_bias.upper())
                or (side is SignalSide.SELL and "BEARISH" in qt_bias.upper())
                or qt_bias.upper() == "NEUTRAL"
            )
        elif daily_q.q == "Q3":
            qt_aligned = (
                (side is SignalSide.BUY and "BULLISH" in qt_bias.upper())
                or (side is SignalSide.SELL and "BEARISH" in qt_bias.upper())
            )
        if qt_aligned:
            score += 1
            confluences.append(f"Quarterly Theory aligned ({daily_q.code} {qt_bias})")

        # ---- Strict-mode hard gates: must have IDM, M5 confirm, score >= threshold.
        # QT alignment is a bonus (counted in score) but not a hard gate.
        if strict:
            if not idm_ok or not m5_confirmed:
                continue
            if score < STRICT_MIN_SCORE:
                continue
            if not news_clear:
                continue

        signal = TradeSignal(
            symbol=ctx.symbol,
            side=side,
            quality=_quality_from_score(score),
            score=score,
            entry=_round(entry, ctx.symbol),
            stop_loss=_round(sl, ctx.symbol),
            tp1=_round(tp1, ctx.symbol),
            tp2=_round(tp2, ctx.symbol),
            tp3=_round(tp3, ctx.symbol),
            rr1=round(rr1, 2),
            rr2=round(rr2, 2),
            rr3=round(rr3, 2),
            poi=poi,
            htf_trend=htf_trend,
            confluences=confluences,
            notes=poi.notes,
        )
        out.append(signal)

    return out
