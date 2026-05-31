# Hyperdress.AI

Hyperdress.AI 是一个面向 Hyperliquid 的异常地址监控工具，核心目标是把重点钱包的仓位变化、强平风险和异常交易信号变成可读、可追踪、可告警的数据流。

当前 MVP 包含：

- 任意钱包地址的 Hyperliquid 永续仓位监控
- 本地 Web 面板展示账户权益、保证金、未实现盈亏、仓位方向、杠杆、强平价和强平距离
- 风险阈值配置与强平距离告警
- FastAPI 后端代理 Hyperliquid Info API，避免浏览器 CORS 问题
- SQLite 保存仓位快照与告警事件
- 仓位变化 diff：新开、加仓、减仓、平仓、翻转
- 告警冷却去重，避免 Telegram 重复刷屏
- 可选 Telegram 告警
- Docker 部署骨架

## 快速开始

也可以直接使用脚本：

```powershell
.\scripts\dev.ps1
```

或 macOS/Linux：

```bash
./scripts/dev.sh
```

手动启动：

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Windows PowerShell：

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

## Docker

```bash
cp .env.example .env
docker compose up --build
```

## 配置

主要配置项位于 `.env`：

```text
HYPERLIQUID_INFO_URL=https://api.hyperliquid.xyz/info
MONITOR_INTERVAL_SECONDS=15
LIQUIDATION_ALERT_PERCENT=12
POSITION_CHANGE_ALERT_PERCENT=25
ALERT_COOLDOWN_SECONDS=900
WATCHED_WALLETS=[]
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

`WATCHED_WALLETS` 使用 JSON 数组格式，例如：

```text
WATCHED_WALLETS=["0x0000000000000000000000000000000000000000"]
```

## API

- `GET /api/health`
- `POST /api/info`：原始 Hyperliquid `clearinghouseState` 代理
- `POST /api/state`：归一化账户快照，计算仓位变化，并写入 SQLite
- `GET /api/alerts`：最近告警事件
- `GET /api/position-changes`：最近仓位变化事件

`POST /api/info` 和 `POST /api/state` 请求体：

```json
{
  "user": "0x...",
  "endpoint": "https://api.hyperliquid.xyz/info"
}
```

## 项目结构

```text
app/
  config.py        配置读取
  hyperliquid.py   Hyperliquid API 客户端
  main.py          FastAPI 入口与监控循环
  models.py        数据模型
  notifier.py      Telegram 通知
  risk.py          仓位风险计算
  storage.py       SQLite 存储
public/
  index.html       本地监控面板
  app.js           前端轮询与渲染
  styles.css       页面样式
```
