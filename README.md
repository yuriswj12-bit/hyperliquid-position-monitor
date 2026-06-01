# Hyperdress.AI

Hyperdress.AI is a local Hyperliquid position monitor. It tracks watched wallets, stores snapshots in SQLite, detects liquidation-risk alerts and position changes, and answers Telegram questions through command mode or an optional AI analyst.

Current MVP:

- Monitor any Hyperliquid `0x` wallet.
- Local web dashboard for account value, margin, PnL, open positions, liquidation price, and liquidation distance.
- FastAPI backend proxy for Hyperliquid Info API.
- SQLite snapshots, alerts, and position-change history.
- Position diff detection: opened, closed, increased, reduced, and flipped.
- Alert cooldown to avoid repeated Telegram spam.
- Telegram commands: `/status`, `/positions`, `/alerts`, `/changes`, `/top`.
- Optional Telegram natural-language analyst through Groq's OpenAI-compatible API.
- Database-backed watchlist with wallet names and tags.
- Docker deployment skeleton.

## Quick Start

PowerShell:

```powershell
.\scripts\dev.ps1
```

macOS/Linux:

```bash
./scripts/dev.sh
```

Manual start:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
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

`TELEGRAM_PROXY_URL` is optional, but useful when `api.telegram.org` is not reachable directly.

After the service starts, the bot supports:

- `/status`: monitor configuration and AI status.
- `/positions <wallet>`: refresh and show one wallet's current positions.
- `/positions`: show the latest configured or stored wallet snapshot.
- `/alerts`: recent risk alerts.
- `/changes`: recent position changes.
- `/top`: wallet with the largest latest position value among stored snapshots.
- `/wallets`: database watchlist.
- `/addwallet <wallet> <name>`: add or update a watched wallet.
- `/removewallet <wallet>`: remove a watched wallet.

## AI Analyst

For a free transition path, use Groq:

```text
AI_PROVIDER=groq
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_BASE_URL=https://api.groq.com/openai/v1
AI_PROXY_URL=
```

When `AI_PROVIDER=groq` and `GROQ_API_KEY` is set, normal Telegram text follows this flow:

```text
user natural language -> AI intent/tool selection -> SQLite/Hyperliquid tools -> AI final answer
```

Example Telegram questions:

- `最近告警`
- `最近变化`
- `看看最近仓位价值最大的地址`
- `查一下 0x... 的仓位`
- `这个地址有没有接近强平 0x...`

If the AI call fails or is disabled, the bot falls back to keyword command routing.

## API

- `GET /api/health`
- `POST /api/info`: raw Hyperliquid `clearinghouseState` proxy.
- `POST /api/state`: normalized account snapshot, alerts, and position changes persisted to SQLite.
- `GET /api/alerts`: recent alert events.
- `GET /api/position-changes`: recent position-change events.
- `GET /api/watched-wallets`: list database watchlist wallets.
- `POST /api/watched-wallets`: add or update a wallet.
- `DELETE /api/watched-wallets/{user}`: remove a wallet.

Request body for `POST /api/info` and `POST /api/state`:

```json
{
  "user": "0x...",
  "endpoint": "https://api.hyperliquid.xyz/info"
}
```

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
  risk.py          risk and position-diff logic
  storage.py       SQLite storage
  telegram_bot.py  Telegram commands and natural-language entrypoint
public/
  index.html       local monitor dashboard
  app.js           frontend polling and rendering
  styles.css       page styles
```
