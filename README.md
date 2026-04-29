# 🪙 Forex Alchemist — Discord Trading Bot

A premium Discord bot that analyses **Forex** and **Gold (XAU/USD)** markets and posts
**A-grade trade setups** every day, fusing the strategies from the *Alchemist*,
*MSNR Key Levels (S.Fx -1075)*, *iscTrader*, and *Daye Quarterly Theory* materials.

> Single-price entries · tight stops · 1 layer per setup · 1–5% risk · multi-timeframe confluence.

---

## ✨ What it does

| Capability | Description |
|---|---|
| **MSNR Key Levels** | Detects Support (Classic V), Resistance (Classic A), SBR, RBS, QML, OCL — and tracks **freshness** (unmitigated). |
| **SMC + LIT** | HH / HL / LH / LL structure, BOS, CHOCH, **Inducement (IDM)** check before any POI. |
| **ICT Kill Zones** | Asia range, London KZ, NY AM KZ, NY PM KZ. Setups inside KZ score higher. |
| **Daye Quarterly Theory** | A·M·D·X cycle on Yearly / Monthly / Weekly / Daily / 90-min / Micro. |
| **SMT divergence** | Cross-checks correlated pairs (EUR/GBP, XAU/XAG, DXY, etc.) for institutional confirmation. |
| **PSP** | Precision Swing Point candle confirmation on the LTF. |
| **Beautiful charts** | Annotated candle charts with Entry / SL / TP1-TP3 lines and RR labels. |
| **Daily auto-scan** | Runs at 07:30 & 12:30 UTC and posts only A-grade setups (score ≥ 7/12). |

## 🤖 Slash commands (English UI)

| Command | What it does |
|---|---|
| `/signal <symbol>` | Multi-timeframe analysis on a single pair, returns the best setup + chart. |
| `/scan` | Scan the full watchlist (XAU/USD, EUR/USD, GBP/USD, USD/JPY, AUD/USD). |
| `/levels <symbol>` | List freshest MSNR key levels (Support / Resistance / SBR / RBS / QML / OCL). |
| `/quarterly` | Current Daye Quarterly Theory state across all cycles. |
| `/sessions` | Active ICT kill zone + Asia range high/low. |
| `/about` | Strategy summary. |
| `/help` | Command guide. |

## 🚀 Quick start

```bash
git clone https://github.com/<you>/forex-alchemist-bot.git
cd forex-alchemist-bot
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# fill in DISCORD_BOT_TOKEN, TWELVEDATA_API_KEY, SIGNAL_CHANNEL_IDS

alchemist-bot
```

### Discord bot setup

1. https://discord.com/developers/applications → **New Application** → **Bot** → *Reset Token*.
2. Enable: **MESSAGE CONTENT INTENT** (optional), **SERVER MEMBERS INTENT**.
3. **OAuth2 → URL Generator**: scopes `bot`, `applications.commands`. Permissions: *Send Messages*, *Embed Links*, *Attach Files*, *Use Slash Commands*, *Read Message History*.
4. Open the generated URL → invite the bot to your server.
5. Copy the channel ID(s) you want daily signals in → put into `SIGNAL_CHANNEL_IDS` (comma separated).

### TwelveData

Free at https://twelvedata.com → Dashboard → copy API key. Free tier = 800 req / day, 8 req / min.

## 🛫 Deploy to Fly.io

```bash
flyctl launch --no-deploy           # accept the existing fly.toml when asked
flyctl secrets set \
    DISCORD_BOT_TOKEN=xxx \
    TWELVEDATA_API_KEY=yyy \
    SIGNAL_CHANNEL_IDS=123,456
flyctl deploy
```

The bot is a long-running worker — no HTTP endpoint is exposed.

## 🧪 Tests

```bash
pytest -q
ruff check src tests
mypy src
```

## 🧭 Strategy reference

The `src/alchemist_bot/strategy/` package implements every piece of the doctrine:

| File | Maps to |
|---|---|
| `structure.py` | SMC market structure, BOS / CHOCH, swing labelling |
| `levels.py` | MSNR Key Levels with **fresh / mitigated** tracking |
| `liquidity.py` | LIT — sweeps, equal H/L pools, **Inducement** rule |
| `sessions.py` | ICT Kill Zones + Asia range |
| `quarterly.py` | Daye AMD/X across Yearly → Micro cycles |
| `smt.py` | Sequential SMT divergence between correlated pairs |
| `signal.py` | Aggregator — final score 0..12 → A+ / A / B / C |

## ⚠️ Disclaimer

This bot is an educational signal-research tool. It does not place orders. Markets carry risk;
trade with capital you can afford to lose, follow the 1–5 % risk rule, and verify every setup
manually before acting on it.
