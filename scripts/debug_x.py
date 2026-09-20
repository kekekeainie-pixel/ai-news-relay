#!/usr/bin/env python3
"""
X (Twitter) cookie 诊断 —— 在 GitHub Actions（境外）上运行，区分 403 的真实病因：
  A. cookie 本身失效/被标记 → 简单 REST 端点也会 401/403
  B. twscrape 的 GraphQL doc_id 过期 → REST 通，GraphQL 403
  C. 账号需要激活 → account/settings.json 返回 200 但 GraphQL 拒

用法：python scripts/debug_x.py
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

COOKIES = os.environ.get("X_COOKIES", "").strip()
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# twscrape 内置的公开 bearer（web 端固定值）
BEARER = ("AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
          "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")


def hdr(extra=None):
    return {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "authorization": f"Bearer {BEARER}",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "Referer": "https://x.com/",
        "Origin": "https://x.com",
        "Cookie": COOKIES,
        **(extra or {}),
    }


def probe(url, label, headers=None, method="GET"):
    req = urllib.request.Request(url, headers=headers or hdr(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read(1200)
            print(f"[{label}] HTTP {r.status} | {body[:200].decode('utf-8','ignore')}")
            return r.status, body
    except urllib.error.HTTPError as e:
        body = e.read(600)
        print(f"[{label}] HTTP {e.code} {e.reason} | {body[:200].decode('utf-8','ignore')}")
        return e.code, body
    except Exception as e:
        print(f"[{label}] {type(e).__name__}: {str(e)[:120]}")
        return 0, b""


def parse_cookies(v):
    return dict(x.strip().split("=", 1) for x in v.split(";") if "=" in x)


def main():
    print("=" * 60)
    print("X cookie 诊断（在 Actions runner 上跑）")
    print("=" * 60)
    if not COOKIES:
        print("❌ X_COOKIES 为空")
        return
    ck = parse_cookies(COOKIES)
    print(f"cookie 键: {sorted(ck.keys())}")
    print(f"auth_token 长度: {len(ck.get('auth_token',''))}")
    print(f"ct0 长度: {len(ck.get('ct0',''))}")
    csrf = ck.get("ct0", "")
    print()

    # 1) 最简单的 cookie 有效性验证：account/settings
    print("--- 1) cookie 有效性（api.x.com/1.1/account/settings.json）---")
    probe("https://api.x.com/1.1/account/settings.json", "account/settings")

    # 2) 验证 GraphQL 是否可用（x.com/i/api/graphql 的 UserByScreenName）
    print("\n--- 2) GraphQL 连通性（不加 doc_id 应返回 400/404 而非 403）---")
    probe("https://x.com/i/api/graphql/UserByScreenName", "graphql-bare",
          headers=hdr({"x-csrf-token": csrf}))

    # 3) 用 twscrape 自己跑（带完整事务 id 生成）
    print("\n--- 3) twscrape 实测 ---")
    try:
        import twscrape
        print("twscrape 版本:", getattr(twscrape, "__version__", "?"))
    except ImportError:
        print("twscrape 未安装")
        return
    import asyncio
    from twscrape import API

    async def run():
        api = API()
        try:
            await api.pool.add_account_cookies(
                os.environ.get("X_USERNAME", "relay"), COOKIES)
        except Exception as e:
            print("add_account_cookies:", type(e).__name__, str(e)[:100])
        try:
            info = await api.pool.accounts_info()
            for k, v in (info.items() if isinstance(info, dict) else []):
                print(f"  account[{k}]: active={v.get('active')} locks={v.get('locks')}")
        except Exception as e:
            print("accounts_info:", type(e).__name__, str(e)[:100])
        # 单次用户查询，短超时
        try:
            u = await asyncio.wait_for(api.user_by_login("sama"), timeout=40)
            print("user_by_login(sama):", u.id if u else None, u.username if u else None)
        except asyncio.TimeoutError:
            print("user_by_login: 超时 40s（多半是队列锁死等待）")
        except Exception as e:
            print("user_by_login:", type(e).__name__, str(e)[:150])

    asyncio.run(run())
    print("\n=== 诊断结束 ===")
    print("判读：REST 通 + GraphQL 403 → doc_id/事务id 过期（twscrape 需升级或换库）")
    print("      REST 也 401/403 → cookie 失效或被风控标记")


if __name__ == "__main__":
    main()
