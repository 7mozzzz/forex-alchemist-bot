"""Beautiful annotated trade-setup charts using mplfinance."""
from __future__ import annotations

import io
from pathlib import Path

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from ..strategy.signal import SignalSide, TradeSignal

# Premium dark theme.
_BG = "#0b0f1a"
_GRID = "#1c2333"
_FG = "#e8edf6"
_BULL = "#22c55e"
_BEAR = "#ef4444"
_GOLD = "#f5b342"

_STYLE = mpf.make_mpf_style(
    marketcolors=mpf.make_marketcolors(
        up=_BULL, down=_BEAR,
        edge={"up": _BULL, "down": _BEAR},
        wick={"up": _BULL, "down": _BEAR},
        volume={"up": "#1e7a3a", "down": "#7a1e1e"},
    ),
    facecolor=_BG,
    edgecolor=_GRID,
    figcolor=_BG,
    gridcolor=_GRID,
    gridstyle="--",
    rc={
        "axes.labelcolor": _FG,
        "axes.edgecolor": _GRID,
        "xtick.color": _FG,
        "ytick.color": _FG,
        "axes.titlecolor": _FG,
        "font.size": 10,
    },
)


def render_signal_chart(
    df: pd.DataFrame,
    signal: TradeSignal,
    timeframe_label: str,
    out_path: str | Path | None = None,
    bars: int = 120,
) -> bytes:
    """Render an annotated chart and return PNG bytes.

    Annotations: entry / SL / TP1-3 horizontal lines + side-of-trade banner.
    """
    plot_df = df.iloc[-bars:].copy()
    plot_df.index.name = "Date"

    color_buy = _BULL
    color_sell = _BEAR
    side_color = color_buy if signal.side is SignalSide.BUY else color_sell

    hlines = dict(
        hlines=[signal.entry, signal.stop_loss, signal.tp1, signal.tp2, signal.tp3],
        colors=[_GOLD, color_sell, color_buy, color_buy, color_buy],
        linestyle=["-", "--", ":", ":", ":"],
        linewidths=[1.6, 1.4, 1.0, 1.0, 1.0],
    )

    fig, axes = mpf.plot(
        plot_df,
        type="candle",
        style=_STYLE,
        hlines=hlines,
        figsize=(11, 6),
        returnfig=True,
        tight_layout=True,
        ylabel="Price",
        datetime_format="%m-%d %H:%M",
        xrotation=15,
    )
    ax = axes[0]
    title = f"{signal.symbol}  •  {timeframe_label}  •  {signal.side.value} {signal.quality.value}"
    ax.set_title(title, color=_FG, fontsize=13, fontweight="bold", pad=12)

    # Right-side annotations
    xlim = ax.get_xlim()
    x_anno = xlim[1] - (xlim[1] - xlim[0]) * 0.02
    for label, price, color in [
        (f"Entry {signal.entry}", signal.entry, _GOLD),
        (f"SL {signal.stop_loss}", signal.stop_loss, color_sell),
        (f"TP1 {signal.tp1} ({signal.rr1}R)", signal.tp1, color_buy),
        (f"TP2 {signal.tp2} ({signal.rr2}R)", signal.tp2, color_buy),
        (f"TP3 {signal.tp3} ({signal.rr3}R)", signal.tp3, color_buy),
    ]:
        ax.annotate(
            label,
            xy=(x_anno, price),
            color=color,
            fontsize=9,
            fontweight="bold",
            ha="right",
            va="center",
            bbox=dict(facecolor=_BG, edgecolor=color, boxstyle="round,pad=0.25", alpha=0.85),
        )

    # Side banner
    ax.text(
        0.012, 0.97,
        f"{signal.side.value}  •  Score {signal.score}/12  •  {signal.poi.kind.value}",
        transform=ax.transAxes,
        color="#0b0f1a",
        fontsize=10,
        fontweight="bold",
        bbox=dict(facecolor=side_color, edgecolor="none", boxstyle="round,pad=0.5"),
        ha="left", va="top",
    )

    fig.text(0.5, 0.01, "Forex Alchemist  •  MSNR + SMC + LIT + ICT + QT + SMT",
             ha="center", color="#7d8aa3", fontsize=8)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=140, facecolor=_BG)
    plt.close(fig)
    buf.seek(0)
    data = buf.read()
    if out_path is not None:
        Path(out_path).write_bytes(data)
    return data
