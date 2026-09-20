# AI News Relay

让国内云端 Hermes 读到**境内访问不到**的 AI 信息源。

## 为什么

云端军师（腾讯云广州）实测被网络阻断的源：
- `x.com` / `twitter.com` — 全不通
- `bsky.app` / `public.api.bsky.app` — 全不通
- `reddit.com` — 全不通
- `www.google.com` — 全不通
- Nitter 全家族、RSSHub 公共实例 — 全不通

而 **GitHub Actions 的 runner 在境外**，能直连这些站点。

## 怎么工作

```
GitHub Actions（境外 runner，定时/手动）
   ↓ 抓 Bluesky / Reddit / HN / RSSHub-X / twscrape-X
   ↓ 写入 data/latest.json 并 commit
云端军师
   ↓ raw.githubusercontent.com 拉取（✅ 实测 0.5s 通）
   ↓ 并入日报候选池
```

## 输出格式

`data/latest.json`：

```json
{
  "generated_at": "2026-09-20T10:00:00+00:00",
  "count": 123,
  "stats": [{"source": "Bluesky KOL", "count": 12, "note": ""}],
  "items": [
    {"source": "Bluesky Andrej Karpathy", "title": "...", "url": "...", "ts": 1789000000, "desc": "..."}
  ]
}
```

`ts` = unix 秒；`ts=0` 表示该源无时间信息（下游需自行判时效）。

## 各源凭证要求

| 源 | 凭证 | 状态 |
|---|---|---|
| Bluesky KOL | **无需** | 默认可用 |
| Hacker News | **无需** | 默认可用 |
| Reddit | **无需** | 默认可用 |
| RSSHub X 路由 | **无需**（公共实例多半已失效） | 有就抓 |
| X/Twitter (twscrape) | **需 `X_COOKIES` secret** | 未配置则跳过 |

### 配置 X_COOKIES（可选，抓 X 用）

仓库 → Settings → Secrets and variables → Actions → New repository secret：
- Name: `X_COOKIES`
- Value: 一个 X 小号的完整 cookie 字符串（`auth_token=...; ct0=...`）

⚠️ 用**小号**，不要用主号；cookie 会过期（数周~数月），失效后需更新。

## 手动触发

Actions → AI News Relay → Run workflow

## 本地跑

```bash
python scripts/fetch_relay.py
```


## X（推特）抓取方案

完整实测方案见 [`docs/X-GRAB.md`](docs/X-GRAB.md) —— 不用 twscrape/Nitter/付费 API，
用一个 X 小号 cookie + GitHub Actions 即可（实测 10 账号 126 条）。

**命门**：cookie 的 `ct0` 必须同时作为 `x-csrf-token` 请求头发送，否则 403。
