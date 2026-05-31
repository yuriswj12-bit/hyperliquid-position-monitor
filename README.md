# Hyperdress.AI

**Hyperdress.AI** 是一个以「异常地址监控 + Telegram 告警」为核心，结合 **AI 聊天分析** 的 Hyperliquid 工具。

## 项目简介

在 Hyperliquid 上，关键地址（尤其是空头地址）的仓位异动往往包含重要信号。但目前缺乏简单、实时的监控与分析工具。

**Hyperdress.AI** 解决了这个问题：
- 后台持续监控你配置的地址
- 出现重要异动时通过 **Telegram** 自动推送告警
- 你可以通过本地聊天框，用自然语言向 AI 提问，快速获取统计数据和洞察

## 核心功能（MVP）

- 后台地址监控（WebSocket）
- Telegram 异动告警（平仓、大额新建、显著加减仓、协同建仓）
- AI 聊天分析（支持统计类问题、查询当前持仓、历史交易）
- 极简本地网页（以聊天框为主交互）
- Docker 一键部署

## 项目结构
<img width="1263" height="588" alt="image" src="https://github.com/user-attachments/assets/0e27b8f6-8332-41fc-aece-56f49416ab84" />


## 快速开始

```bash
git clone https://github.com/yuriswj12-bit/hyperliquid-position-monitor.git
cd hyperliquid-position-monitor

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt

文档
完整的产品方案文档请查看：

PRODUCT_SPEC.md

状态
MVP 开发中
目标：做一个能稳定监控 + 通过对话交互分析的交易工具。
