#!/usr/bin/env python3
"""
AI News Relay — 在 GitHub Actions（境外 runner）上抓取境内读不到的源，
输出 JSON 供国内云端 Hermes 通过 raw.githubusercontent.com 读取。

本次覆盖：
  1. Bluesky 公开 API（无需任何凭证）—— AI 大佬动态
  2. RSSHub 公共实例的 X/Twitter 路由（能通就抓，不通就跳过）
  3. X/Twitter 通过 twscrape + 账号 Cookie（若配置了 X_COOKIES secret）
  4. Hacker News / Reddit（论坛讨论，境内不通，这里补）

输出：data/latest.json —— 统一的条目格式
  {"generated_at": ..., "items": [{"source","title","url","ts","desc"}]}

设计原则：
  * 每个源独立 try/except，单个挂掉不影响整体
  * 无凭证时优雅降级（Bluesky 永远可跑）
  * 时间戳统一为 unix 秒
"""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

TIMEOUT = 25
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36"}
ITEMS = []
STATS = []


def log(*a):
    print(*a, flush=True)


def http(url, timeout=TIMEOUT, headers=None, data=None, method=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def add(source, title, url, ts, desc=""):
    if not title:
        return
    ITEMS.append({
        "source": source,
        "title": title.strip()[:300],
        "url": url or "",
        "ts": int(ts or 0),
        "desc": (desc or "").strip()[:400],
    })


# ------------------------------------------------------------------
# 1) Bluesky 公开 API（无需凭证）
# ------------------------------------------------------------------
BSKY_KOLS = [
    # handle, 显示名
    ("karpathy.bsky.social", "Andrej Karpathy"),
    ("simonwillison.net", "Simon Willison"),
    ("natolambert.bsky.social", "Nathan Lambert"),
    ("emollick.bsky.social", "Ethan Mollick"),
]

BSKY_SEARCH_TERMS = ["AI", "LLM", "open source model"]


def fetch_bluesky():
    n = 0
    for handle, name in BSKY_KOLS:
        try:
            u = ("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?"
                 + urllib.parse.urlencode({"actor": handle, "limit": 10}))
            j = json.loads(http(u))
            for f in j.get("feed", []):
                p = f.get("post", {})
                rec = p.get("record", {})
                txt = rec.get("text") or ""
                if not txt.strip():
                    continue
                created = rec.get("createdAt") or ""
                ts = 0
                if created:
                    ts = datetime.fromisoformat(created.replace("Z", "+00:00")).timestamp()
                rk = (p.get("uri") or "").split("/")[-1]
                url = f"https://bsky.app/profile/{handle}/post/{rk}" if rk else ""
                add(f"Bluesky {name}", txt.replace("\n", " ")[:200], url, ts, txt[:300])
                n += 1
        except Exception as e:
            log(f"  [bsky:{handle}] {type(e).__name__}: {str(e)[:80]}")
    STATS.append(("Bluesky KOL", n, ""))
    log(f"  Bluesky KOL: {n}")


# ------------------------------------------------------------------
# 2) RSSHub 公共实例（X 路由，能通就抓）
# ------------------------------------------------------------------
RSSHUB_INSTANCES = [
    "https://rsshub.app",
    "https://rsshub.rssforever.com",
    "https://rsshub.pseudoyu.com",
    "https://rsshub.ktachibana.party",
]

X_KOLS = ["sama", "karpathy", "OpenAI", "AnthropicAI", "GoogleDeepMind", "ylecun"]

# 关键词搜索（主人 09-20 要求：大佬动态 + AI 关键词都要）
X_SEARCH_TERMS = ["AI model release", "LLM open source", "AI agent"]


def fetch_rsshub():
    n = 0
    working = None
    for inst in RSSHUB_INSTANCES:
        try:
            http(inst + "/", timeout=10)
            working = inst
            log(f"  RSSHub 可用实例: {inst}")
            break
        except Exception:
            continue
    if not working:
        STATS.append(("RSSHub X", 0, "无可用实例"))
        log("  RSSHub: 无可用实例")
        return
    import xml.etree.ElementTree as ET
    for user in X_KOLS:
        try:
            raw = http(f"{working}/twitter/user/{user}", timeout=20)
            root = ET.fromstring(raw)
            cnt = 0
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                pd = it.findtext("pubDate") or ""
                ts = 0
                if pd:
                    try:
                        ts = datetime.strptime(pd, "%a, %d %b %Y %H:%M:%S %Z").replace(
                            tzinfo=timezone.utc).timestamp()
                    except Exception:
                        ts = 0
                add(f"X @{user}", title[:200], link, ts)
                cnt += 1
                n += 1
                if cnt >= 10:
                    break
        except Exception as e:
            log(f"  [rsshub:{user}] {type(e).__name__}")
    STATS.append(("RSSHub X", n, working))


# ------------------------------------------------------------------
# 3) Hacker News（论坛讨论）
# ------------------------------------------------------------------
def fetch_hn():
    n = 0
    try:
        start = int(time.time()) - 48 * 3600
        u = ("https://hn.algolia.com/api/v1/search?query=AI&tags=story&hitsPerPage=30"
             f"&numericFilters=created_at_i%3E{start}")
        j = json.loads(http(u))
        for h in j.get("hits", []):
            t = h.get("title") or ""
            if t:
                add("HN", t, h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                    h.get("created_at_i", 0), f"{h.get('points', 0)} points")
                n += 1
    except Exception as e:
        log(f"  [hn] {type(e).__name__}: {str(e)[:60]}")
    STATS.append(("HN", n, ""))
    log(f"  HN: {n}")


# ------------------------------------------------------------------
# 4) Reddit（境内不通，runner 可通）
# ------------------------------------------------------------------
REDDIT_SUBS = ["LocalLLaMA", "MachineLearning", "artificial", "OpenAI"]


def fetch_reddit():
    n = 0
    for sub in REDDIT_SUBS:
        try:
            u = f"https://www.reddit.com/r/{sub}/hot.json?limit=15"
            j = json.loads(http(u, timeout=20))
            for c in j.get("data", {}).get("children", []):
                d = c.get("data", {})
                title = d.get("title") or ""
                if not title or d.get("stickied"):
                    continue
                add(f"Reddit r/{sub}", title, "https://reddit.com" + (d.get("permalink") or ""),
                    d.get("created_utc", 0), f"{d.get('score', 0)} pts")
                n += 1
        except Exception as e:
            log(f"  [reddit:{sub}] {type(e).__name__}: {str(e)[:60]}")
    STATS.append(("Reddit", n, ""))
    log(f"  Reddit: {n}")


# ------------------------------------------------------------------
# 5) X/Twitter via twscrape（需 X_COOKIES secret，可选）
# ------------------------------------------------------------------
def fetch_twitter():
    """X/Twitter via 自建客户端（x_client.py）—— 不依赖 twscrape。
    ★ 命门：cookie 的 ct0 必须同时作为 x-csrf-token 头发送。"""
    cookies = os.environ.get("X_COOKIES", "").strip()
    if not cookies:
        STATS.append(("X", 0, "未配置 X_COOKIES"))
        log("  X: 跳过（未配置 X_COOKIES）")
        return
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        from x_client import XClient, X_KOLS
    except Exception as e:
        STATS.append(("X", 0, f"导入失败 {type(e).__name__}"))
        log(f"  X: 导入 x_client 失败 {e}")
        return
    try:
        cli = XClient(cookies)
        n = 0
        for u in X_KOLS:
            uid, note = cli.user_id(u)
            if not uid:
                log(f"  [x:{u}] ✗ {note}")
                continue
            tws, err = cli.user_tweets(uid, 20)
            if err:
                log(f"  [x:{u}] ✗ {err}")
                continue
            got = 0
            for t in tws:
                add(f"X @{u}", t["text"].replace("\n", " ")[:250], t["url"],
                    int(t["ts"]), t["text"][:400])
                got += 1
                n += 1
            log(f"  [x:{u}] {got} 条")
            time.sleep(1.0)
        STATS.append(("X (自建客户端)", n, f"{len(X_KOLS)} 账号"))
        log(f"  X: {n}")
    except Exception as e:
        STATS.append(("X", 0, f"{type(e).__name__}"))
        log(f"  X 失败: {type(e).__name__}: {str(e)[:120]}")


def main():
    log(f"=== AI News Relay 启动 {datetime.now(timezone.utc).isoformat()} ===")
    for fn in (fetch_twitter, fetch_bluesky, fetch_rsshub, fetch_hn, fetch_reddit):
        try:
            fn()
        except Exception as e:
            log(f"  [{fn.__name__}] 顶层异常 {type(e).__name__}: {str(e)[:100]}")
    # 去重（同 url 或同标题前 40 字）
    seen, uniq = set(), []
    for it in ITEMS:
        k = it["url"] or re.sub(r"\W", "", it["title"])[:40]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(it)
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(uniq),
        "stats": [{"source": s, "count": c, "note": n} for s, c, n in STATS],
        "items": uniq,
    }
    os.makedirs("data", exist_ok=True)
    with open("data/latest.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    log(f"=== 完成：{len(uniq)} 条 → data/latest.json ===")
    for s, c, n in STATS:
        log(f"    {s:<18} {c:>4}  {n}")


if __name__ == "__main__":
    main()
