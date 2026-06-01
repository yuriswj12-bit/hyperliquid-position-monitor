# Hyperdress.AI Product Spec

## Goal

Hyperdress.AI monitors important Hyperliquid wallet addresses, records position state over time, detects liquidation risk and abnormal position changes, and makes the data queryable through a web dashboard and Telegram.

The current product direction is:

```text
user natural language -> AI understanding -> tool/database analysis -> AI-generated reply
```

The AI layer must not invent market or wallet data. It should call local tools backed by SQLite snapshots, recent alerts, recent position changes, and live Hyperliquid refreshes.

## User Scenarios

- A trader monitors whether key wallets are approaching liquidation.
- A researcher tracks opened, closed, increased, reduced, or flipped positions.
- A team receives high-risk Telegram alerts.
- A user asks natural-language questions such as "最近仓位价值最大的地址是谁" or "这个地址有没有接近强平".
- A user manages a named watchlist instead of editing `.env` for every address change.

## MVP Scope

### Wallet Monitoring

- Configure one or more `0x` wallet addresses.
- Add, update, list, and remove database-backed watched wallets.
- Store wallet name, tags, notes, and timestamps.
- Poll Hyperliquid `clearinghouseState`.
- Store account value, position value, margin usage, withdrawable balance, unrealized PnL, and raw response data.

### Risk Detection

- Calculate each position's distance to liquidation price.
- Mark `critical` and `warning` alerts using `LIQUIDATION_ALERT_PERCENT`.
- Persist alert events.
- Use `ALERT_COOLDOWN_SECONDS` to deduplicate repeated alerts.

### Position Changes

- Compare the previous and current snapshot for the same wallet.
- Detect `opened`, `closed`, `flipped`, `increased`, and `reduced`.
- Use `POSITION_CHANGE_ALERT_PERCENT` to control increased/reduced sensitivity.
- Store position-change events in SQLite for Telegram and AI analysis.

### Wallet History Summary

- Summarize stored snapshots for one wallet over a configurable time window.
- Report snapshot count, total stored snapshots, latest account metrics, and first-to-latest deltas.
- Report nearest liquidation distance from the latest open positions when available.
- Explicitly mark whether there are at least two snapshots in the window, so AI can avoid overclaiming trends when data is sparse.

### Web Dashboard

- Query a wallet from the browser.
- Display account summary and open positions.
- Show liquidation distance and risk status.
- Allow custom refresh interval, API endpoint, and risk threshold.

### Telegram Bot

- Enable with `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`.
- Send concise liquidation-risk alerts.
- Support command queries: `/status`, `/positions`, `/alerts`, `/changes`, `/top`.
- Support history summary query: `/summary <wallet> [hours]`.
- Support watchlist commands: `/wallets`, `/addwallet`, `/removewallet`.
- Support manual watchlist refresh with `/refreshwallets`.
- Support natural-language questions through the AI analyst when configured.
- Fall back to keyword routing if AI is disabled or unavailable.

### AI Analyst

- Free transition provider: Groq OpenAI-compatible API.
- Enabled with `AI_PROVIDER=groq` and `GROQ_API_KEY`.
- Available tools:
  - latest stored positions
  - live wallet refresh
  - recent alerts
  - recent position changes
  - wallet with largest latest position value
  - watched-wallet list management
  - watchlist data refresh
  - wallet history summary and data sufficiency
- The final reply should be short, fact-based, and in the user's language.

## Non-MVP Scope

- Automatic trading or order placement.
- Private key custody.
- Multi-user permission system.
- Strategy backtesting.
- Full autonomous AI agent workflow.

## Data Model

### Snapshot

- `user`
- `captured_at`
- `account_value`
- `total_position_value`
- `total_margin_used`
- `withdrawable`
- `unrealized_pnl`
- `raw_json`

### Alert

- `user`
- `coin`
- `severity`
- `message`
- `created_at`
- `fingerprint`

### Position Change

- `user`
- `coin`
- `change_type`
- `previous_size`
- `current_size`
- `previous_value`
- `current_value`
- `change_percent`
- `message`
- `created_at`

### Watched Wallet

- `user`
- `name`
- `tags`
- `notes`
- `created_at`
- `updated_at`

## Roadmap

1. Wallet groups and richer labels.
2. Per-wallet historical summaries.
3. More Telegram report templates.
4. AI memory over saved snapshots and changes.
5. WebSocket data source for lower latency.
6. Deployment health checks and production hosting.
