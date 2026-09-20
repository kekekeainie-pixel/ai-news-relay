#!/usr/bin/env python3
"""
探测 X 的「无库」抓取路径 —— 绕开 twscrape 的 doc_id 问题。

思路：X 为「嵌入时间线」提供了服务端渲染接口，**不需要 API key、不需要 doc_id**：
  - https://syndication.twitter.com/srv/timeline-profile/screen-name/<user>
  - https://cdn.syndication.twimg.com/tweet-result?id=<tweet_id>&token=x

若这些能返回推文，就不必依赖 twscrape。

在 GitHub Actions（境外 runner）上运行：python scripts/probe_x_paths.py
"""
import json
import os
import re
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
COOKIES = os.environ.get("X_COOKIES", "").strip()


def get(url, headers=None, timeout=25):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9",
         "Referer": "https://x.com/", **(headers or {})}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read(500)
    except Exception as e:
        return 0, f"{type(e).__name__}: {str(e)[:100]}".encode()


def show(label, status, body, extra=""):
    if isinstance(body, bytes):
        txt = body.decode("utf-8", "ignore")
    else:
        txt = str(body)
    print(f"[{label}] HTTP {status} len={len(txt)} {extra}")
    if txt.strip():
        print("   ", txt[:180].replace("\n", " "))
    return txt


def main():
    print("=" * 62)
    print("X 无库抓取路径探测")
    print("=" * 62)

    # ---- 路径 1: syndication 嵌入时间线（无需认证）----
    print("\n--- 路径1: syndication.twitter.com 嵌入时间线 ---")
    for user in ["sama", "karpathy", "OpenAI"]:
        st, body = get(f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{user}")
        txt = show(f"syndication/{user}", st, body)
        if st == 200 and txt:
            # 找内嵌 JSON
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', txt, re.S)
            if m:
                try:
                    data = json.loads(m.group(1))
                    entries = (data.get("props", {}).get("pageProps", {})
                                   .get("timeline", {}).get("entries", []))
                    print(f"    ✅ __NEXT_DATA__ 解析成功，entries={len(entries)}")
                    n = 0
                    for e in entries[:5]:
                        c = e.get("content", {}).get("tweet", {})
                        t = (c.get("full_text") or c.get("text") or "").replace("\n", " ")
                        if t:
                            print(f"       · {t[:90]}")
                            n += 1
                    if n == 0:
                        print("       (entries 里没找到 full_text，结构可能变了)")
                        print("       entries[0] keys:", list(entries[0].keys()) if entries else "空")
                except Exception as ex:
                    print(f"    ❌ JSON 解析失败: {type(ex).__name__}: {str(ex)[:80]}")
            else:
                print("    ⚠️ 页面里没找到 __NEXT_DATA__")

    # ---- 路径 2: cdn.syndication 单推文 ----
    print("\n--- 路径2: cdn.syndication.twimg.com 单推文 ---")
    st, body = get("https://cdn.syndication.twimg.com/tweet-result?id=1800000000000000000&token=x")
    show("cdn.syndication tweet-result", st, body)

    # ---- 路径 3: X GraphQL 公开的 UserByScreenName（用已知 doc_id）----
    print("\n--- 路径3: GraphQL UserByScreenName（cookie + 已知 doc_id）---")
    # 这个 doc_id 会变；先看返回是 400(参数) 还是 403(权限)
    for did in ["32pL5BWe9WKeSK1MoPvFQQ", "sLVLhk0bGj3MVFEKTdax1w", "G3KGOASz96M-Qu0nwmGXNg"]:
        st, body = get(
            "https://x.com/i/api/graphql/{}/UserByScreenName"
            "?variables=%7B%22screen_name%22%3A%22sama%22%2C%22withSafetyModeUserFields%22%3Atrue%7D"
            "&features=%7B%22hidden_profile_subscriptions_enabled%22%3Atrue%7D".format(did),
            headers={"Cookie": COOKIES, "x-csrf-token": "", "authorization": (
                "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
                "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")})
        show(f"graphql doc_id={did[:12]}", st, body)
        if st == 200:
            print("    ★ 这个 doc_id 有效！")
            break

    # ---- 路径 4: 官方 API v2（需 key，验证是否 401）----
    print("\n--- 路径4: 官方 API v2（无 key 应 401）---")
    st, body = get("https://api.x.com/2/tweets/search/recent?query=AI")
    show("api v2 search", st, body)

    print("\n" + "=" * 62)
    print("判读要点：")
    print("  路径1 若 entries>0 → 直接用嵌入接口，无需 twscrape（最优）")
    print("  路径3 若某个 doc_id 返回 200 → 用 GraphQL + cookie，自己实现")
    print("  路径4 若 401 → 官方 API 必须付费，放弃")
    print("=" * 62)


if __name__ == "__main__":
    main()
