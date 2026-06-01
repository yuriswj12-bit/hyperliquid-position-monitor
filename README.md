# Hyperdress.AI

Hyperdress.AI is a local Hyperliquid position monitor. It tracks watched wallets, stores snapshots and fills in SQLite, detects liquidation-risk alerts and position changes, and answers Telegram questions through command mode or an optional AI analyst.

## Current MVP

- Monitor any Hyperliquid `0x` wallet.
- Local web dashboard for account value, margin, PnL, open positions, liquidation price, and liquidation distance.
- FastAPI backend proxy for Hyperliquid Info API.
- SQLite snapshots, alerts, position changes, watchlist, and fills.
- Position diff detection: opened, closed, increased, reduced, and flipped.
- Alert cooldown to avoid repeated Telegram spam.
- Telegram commands for status, positions, alerts, changes, fills, reports, and wallet management.
- Optional Telegram natural-language analyst through Groq's OpenAI-compatible API.
- Docker deployment skeleton.

## Quick Start

PowerShell:

```powershell
cd C:\Users\hek\Documents\Hyperdress.AI
.\scripts\dev.ps1
```

macOS/Linux:

```bash
./scripts/dev.sh
```

Open:

```text
http://127.0.0.1:8000
```

## Checks

Run local checks without starting the server:

```powershell
.\scripts\check.ps1
```

Run smoke checks against a running server:

```powershell
.\scripts\smoke.ps1
```

Run full smoke checks for one wallet:

```powershell
.\scripts\smoke.ps1 -Wallet 0x0ddf9bae2af4b874b96d287a5ad42eb47138a902
```

## Configuration

Copy `.env.example` to `.env`, then fill the values you need:

```text
HYPERLIQUID_INFO_URL=https://api.hyperliquid.xyz/info
MONITOR_INTERVAL_SECONDS=15
LIQUIDATION_ALERT_PERCENT=12
POSITION_CHANGE_ALERT_PERCENT=25
ALERT_COOLDOWN_SECONDS=900
WATCHED_WALLETS=[]
```

`WATCHED_WALLETS` uses JSON array format:

```text
WATCHED_WALLETS=["0x0000000000000000000000000000000000000000"]
```

## Telegram

Set these in `.env`:

```text
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
TELEGRAM_PROXY_URL=http://127.0.0.1:7897
```

After the service starts, the bot supports:

- `/status`: monitor configuration and AI status.
- `/positions <wallet>`: refresh and show one wallet's current positions.
- `/alerts`: recent risk alerts.
- `/changes`: recent position changes.
- `/fills <wallet>`: Chinese compact grouped fills report, defaulting to 10 fills.
- `/refreshfills <wallet>`: fetch fresh Hyperliquid `userFills` and save new fills.
- `/top`: wallet with the largest latest position value among stored snapshots.
- `/summary <wallet> [hours]`: stored snapshot summary and trend-readiness.
- `/report <wallet> [hours]`: formatted risk report.
- `/wallets`: database watchlist.
- `/addwallet <wallet> <name>`: add or update a watched wallet.
- `/removewallet <wallet>`: remove a watched wallet.
- `/refreshwallets`: refresh every active wallet.

## AI Analyst

For a free transition path, use Groq:

```text
AI_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_BASE_URL=https://api.groq.com/openai/v1
AI_PROXY_URL=
```

When enabled, normal Telegram text follows this flow:

```text
user natural language -> AI intent/tool selection -> SQLite/Hyperliquid tools -> AI final answer
```

Example Telegram questions:

- `最近告警`
- `最近变化`
- `看看最近仓位价值最大的地址`
- `查一下 0x... 的仓位`
- `查看 0x... 最近10条成交`
- `用报告格式分析 0x... 的风险`

If the AI call fails or is disabled, the bot falls back to keyword command routing.

## API

- `GET /api/health`
- `POST /api/info`: raw Hyperliquid `clearinghouseState` proxy.
- `POST /api/state`: normalized account snapshot, alerts, and position changes persisted to SQLite.
- `POST /api/fills`: fetch and store Hyperliquid `userFills`.
- `GET /api/fills`: recent stored fills, optionally filtered by `user`.
- `GET /api/alerts`: recent alert events.
- `GET /api/position-changes`: recent position-change events.
- `GET /api/wallets/{user}/summary`: stored snapshot summary for one wallet.
- `GET /api/wallets/{user}/position-changes`: recent position changes for one wallet.
- `GET /api/watched-wallets`: list database watchlist wallets.
- `POST /api/watched-wallets`: add or update a wallet.
- `POST /api/watched-wallets/refresh`: refresh all active wallets.
- `DELETE /api/watched-wallets/{user}`: remove a wallet.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

## Project Structure

```text
app/
  ai_analyst.py    Groq/OpenAI-compatible tool-calling analyst
  config.py        environment configuration
  hyperliquid.py   Hyperliquid API client
  main.py          FastAPI entrypoint and monitor loop
  models.py        data models
  notifier.py      Telegram alert sender
  reporting.py     compact Telegram/AI report formatting
  risk.py          risk and position-diff logic
  storage.py       SQLite storage
  telegram_bot.py  Telegram commands and natural-language entrypoint
public/
  index.html       local monitor dashboard
  app.js           frontend polling and rendering
  styles.css       page styles
scripts/
  dev.ps1          create env, install deps, start server
  check.ps1        local compile/import/storage/report checks
  smoke.ps1        HTTP smoke checks against a running server
```
