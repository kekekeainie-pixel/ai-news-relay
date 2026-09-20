# 在 GitHub Actions 上抓 X（推特）—— 2026-09-20 实测跑通

> 结论：**不需要 twscrape / snscrape / Nitter / RSSHub，不需要付费 API。**
> 只需要一个 X 小号的 cookie（`auth_token` + `ct0`）+ GitHub Actions 的境外 runner。
> 实测 10 个 AI 账号抓到 **126 条真推文**（2026-09-20）。

---

## 一、为什么必须绕（网络事实，实测）

云端服务器（腾讯云·广州）对境外社媒是 **三层封锁**：

| 层 | 现象 | 证据 |
|---|---|---|
| DNS 污染 | `xcancel.com` → 解析到 Facebook 的 IP | 换 8.8.8.8 / 1.1.1.1 都不救 |
| 路由封锁 | 用公共 DNS 拿**真 IP** 直连 → 仍超时 | TCP 连不上 |
| SNI 阻断 | `x.com` **TCP 通了**（0.2s），SSL 握手死 | 无法完成 TLS |

**实测不通**：`x.com` / `twitter.com` / `api.x.com` / `bsky.app` / `reddit.com` / `google.com` /
Nitter 全家族（nitter.net、xcancel、tiekoetter、space、lightbrd）/ RSSHub 公共实例 / `telegram.org`。
**实测能通**：`github.com`（慢，15s）、`api.github.com`（0.3s）、`raw.githubusercontent.com`（0.5s）。

→ **GitHub Actions 的 runner 在境外**，所以它是唯一可用的中转。

---

## 二、抓 X 的命门（本文最重要的一条）

```
X GraphQL 返回 403：
  {"errors":[{"code":353,"message":"This request requires a matching csrf cookie and header."}]}
```

**原因**：cookie 里的 `ct0` **必须同时作为 `x-csrf-token` 请求头**发送。
只把 cookie 塞进 `Cookie:` 头是不够的。

### 必须的请求头

```python
{
  "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
                   "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",   # web 端固定 bearer
  "x-csrf-token": ct0,                                  # ★★ 命门，不写这行必 403
  "x-twitter-active-user": "yes",
  "x-twitter-auth-type": "OAuth2Session",
  "x-twitter-client-language": "en",
  "Referer": "https://x.com/",
  "Origin": "https://x.com",
  "Cookie": f"auth_token={auth_token}; ct0={ct0}",
}
```

### 可用的 doc_id（会变，失效就重新找）

```
UserByScreenName = 32pL5BWe9WKeSK1MoPvFQQ
UserTweets       = V7H0Ap3_Hh2FyS75OCDO3Q
```

- 长推文正文在 `note_tweet.note_tweet_results.result.text`，不是 `legacy.full_text`
- 要 `unwrap()` 掉 `TweetWithVisibilityResults` 包装
- 时间线在 `data.user.result.timeline_v2.timeline.instructions[].entries[]`

---

## 三、走过的弯路（别重复）

| 尝试 | 结果 | 原因 |
|---|---|---|
| `twscrape`（最流行的库） | ❌ 403 / 队列锁死 15 分钟 | 内置 doc_id 过期；且它把 ct0 只当 cookie |
| `api.x.com/1.1/account/settings` | 404 | v1.1 端点已废弃 |
| `syndication.twitter.com/srv/timeline-profile/screen-name/<user>` | ❌ 429 | 对数据中心 IP 限流 |
| `cdn.syndication.twimg.com/tweet-result` | 404 | 已下线 |
| 官方 API v2 | ❌ 401 | 必须付费（读一条 $0.005） |
| Nitter / RSSHub 公共实例 | ❌ 全不通 | Nitter 2026-08 收律师函关闭；RSSHub 的 X 路由改为「仅自建+cookie」 |
| Bluesky 公开 API | ⚠️ 能抓（39 条）但内容水 | AI 圈不在 Bluesky（Karpathy 号注册 3 年只 20 帖） |
| Reddit `.json` | ❌ runner 被 403 Blocked | Reddit 封数据中心 IP |

---

## 四、完整可用方案（已部署）

仓库 `kekekeainie-pixel/ai-news-relay`（public → Actions 无限免费）

```
GitHub Actions（cron: 每 6 小时，UTC 0/6/12/18:30）
   ├ scripts/x_client.py        自建 X 客户端（本文核心）
   ├ scripts/fetch_relay.py     汇总器：X + Bluesky + HN + Reddit + RSSHub
   └ → data/latest.json 并 commit
云端军师
   └ raw.githubusercontent.com/.../main/data/latest.json  ← 0.7s 读到
```

### 实测产出（2026-09-20）

| 源 | 条数 |
|---|---|
| **X（自建客户端，10 账号）** | **126** |
| Bluesky KOL | 39 |
| HN Algolia | 30 |
| RSSHub X | 0（公共实例已死） |
| Reddit | 0（403） |
| **合计** | **195** |

---

## 五、cookie 怎么拿（给用户的操作步骤）

1. 电脑 Chrome/Edge 打开 `x.com`，登录**小号**（⚠️ 别用主号）
2. `F12` → `Application` 标签
3. 左侧 `Cookies` → `https://x.com`
4. 找 `auth_token`（40 位）和 `ct0`（160 位），双击 Value 复制
5. 拼成一行：`auth_token=xxx; ct0=yyy`
6. 存成仓库 Secret：Settings → Secrets and variables → Actions → `X_COOKIES`

⚠️ cookie 会过期（数周~数月）；失效后重导一次。
⚠️ 用专用小号，风控/封号时不波及主号。

---

## 六、踩坑清单

- **git push 到 GitHub 会莫名失败**（`GnuTLS recv error` / 135s 超时）—— 云端到 `github.com` 主站不稳。
  → 改用 **`gh api` 传文件**（走 `api.github.com`，实测 5.8s 传完两个文件，比 git 快百倍）：
  ```python
  # 取 sha（更新时必需）→ base64 内容 → PUT
  gh api /repos/{owner}/{repo}/contents/{path} --jq .sha
  gh api -X PUT /repos/{owner}/{repo}/contents/{path} --input payload.json
  ```
- **全局 git 有 url 重写**（`github.com` → `ghproxy.net`）→ 推带 token 的 remote 会失败。
  在仓库内局部覆盖：`git config url."https://github.com/".insteadOf "https://ghproxy.net/https://github.com/"`
- **时间窗别设太窄**：72h 窗口让 7/10 个账号显示 0 条（大佬们 3-5 天发一条）。
  先抓回来再让下游筛选，别在抓取层砍。
- **GitHub 设备码登录端点**是 `/login/oauth/access_token`（不是 `/login/access_token`）。
  `gh auth login --web` 在 pty 下会缓冲卡死，直接调 API 更可靠。`github.com` 主站要 60s 超时。
- **登录后 API 额度 60 → 5000/小时**（白捡的好处，GitHub Releases 抓取再也不怕打光）。

---

## 七、验证命令

```bash
# 看 Actions 运行
gh run list --repo kekekeainie-pixel/ai-news-relay --limit 5
gh run view <id> --repo kekekeainie-pixel/ai-news-relay --log

# 本地测 X 客户端（需能上 x.com）
X_COOKIES='auth_token=...; ct0=...' python scripts/x_client.py --hours 0 --limit 20

# 云端读产出
curl -s https://raw.githubusercontent.com/kekekeainie-pixel/ai-news-relay/main/data/latest.json | head -c 500
```
