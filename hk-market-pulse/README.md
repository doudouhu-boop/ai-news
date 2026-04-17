# 港股市场脉搏 - 自动生成器

自动获取港股行情数据，通过 AI Agent 生成市场资讯，定时发布到 GitHub。

## 架构

```
GitHub Actions (cron 定时)
  ├── Longbridge SDK → 获取港股实时行情 + 新闻
  ├── Babbage Agent API → AI 生成市场资讯
  └── Git Push → 文章存入 articles/ 目录
```

## 触发时间（香港时间，周一至周五）

| 时段 | 香港时间 | UTC | 字数要求 |
|------|---------|-----|---------|
| 盘中 | 10:30  | 02:30 | 150-200字 |
| 午评 | 12:10  | 04:10 | 250-300字 |
| 收盘 | 16:10  | 08:10 | 400-500字 |

## 配置 GitHub Secrets

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| Secret | 说明 |
|--------|------|
| `LONGBRIDGE_APP_KEY` | Longbridge 开放平台 App Key |
| `LONGBRIDGE_APP_SECRET` | Longbridge 开放平台 App Secret |
| `LONGBRIDGE_ACCESS_TOKEN` | Longbridge Access Token |
| `BABBAGE_AGENT_URL` | Babbage Agent API 地址 |
| `BABBAGE_API_KEY` | Babbage Agent API Key |

## 文件结构

```
articles/
├── 2026-04-17_intraday.json   # 盘中
├── 2026-04-17_midday.json     # 午评
└── 2026-04-17_close.json      # 收盘
```

## 手动触发

在 GitHub 仓库 → Actions → HK Market Pulse → Run workflow

## 本地测试

```bash
export LONGBRIDGE_APP_KEY="your-key"
export LONGBRIDGE_APP_SECRET="your-secret"
export LONGBRIDGE_ACCESS_TOKEN="your-token"
export BABBAGE_API_KEY="your-babbage-key"
pip install requests longbridge
python scripts/generate.py
```
