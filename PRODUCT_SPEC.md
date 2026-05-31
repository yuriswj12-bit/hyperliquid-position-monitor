# Hyperdress.AI Product Spec

## 目标

Hyperdress.AI 的 MVP 目标是稳定监控 Hyperliquid 上的一组重点地址，并在仓位风险或异常变化出现时给出即时提醒。第一版优先解决“看得见、存得下、能告警”，AI 聊天分析作为第二阶段建立在结构化数据之上。

## 用户场景

- 交易员监控重点地址是否接近强平
- 研究员跟踪空头地址的新开仓、加仓、减仓和平仓
- 团队通过 Telegram 接收高风险仓位提醒
- 后续通过自然语言查询当前持仓、历史变化和统计结论

## MVP 范围

### 地址监控

- 支持配置多个 `0x` 钱包地址
- 周期性请求 Hyperliquid `clearinghouseState`
- 保存账户权益、仓位价值、保证金使用、可提现余额和原始响应

### 风险识别

- 计算每个仓位距离强平价的百分比
- 根据 `LIQUIDATION_ALERT_PERCENT` 标记 `critical` 与 `warning`
- 保存告警事件，避免风险信息只停留在前端

### Web 面板

- 输入钱包地址后实时查看账户摘要
- 展示 open positions 表格
- 展示强平距离与风险提醒
- 支持自定义刷新间隔、API endpoint 和风险阈值

### Telegram 告警

- 配置 `TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID` 后启用
- 对强平距离告警发送简洁文本消息

## 非 MVP 范围

- 自动交易或下单
- 私钥管理
- 多用户权限系统
- 复杂策略回测
- 完整 AI Agent 工作流

## 数据模型

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

## 后续路线

1. 地址分组与标签
2. 仓位变化 diff：新开、加仓、减仓、平仓
3. 告警去重与冷却时间
4. Telegram 命令查询当前仓位
5. AI 聊天分析：基于 SQLite 快照回答统计类问题
6. WebSocket 数据源与更低延迟监控
7. Docker 部署与健康检查完善
