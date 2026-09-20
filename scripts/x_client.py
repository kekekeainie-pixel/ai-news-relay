#!/usr/bin/env python3
"""
自建 X 客户端 —— 不依赖 twscrape（它的 doc_id 已过期）。

关键点（本次实测得出）：
  * cookie 里的 `ct0` 必须**同时**作为 `x-csrf-token` 请求头发送，
    否则 GraphQL 返回 403 code=353 "requires a matching csrf cookie and header"
  * 官方 API v2 无 key → 401，必须付费，放弃
  * syndication 嵌入接口对数据中心 IP 返回 429

用法：X_COOKIES='auth_token=...; ct0=...' python scripts/x_client.py
输出：data/x_debug.json（抓到的推文）
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
BEARER = ("AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
          "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA")


def parse_cookies(v):
    return dict(x.strip().split("=", 1) for x in v.split(";") if "=" in x)


class XClient:
    def __init__(self, cookies_str):
        self.ck = parse_cookies(cookies_str)
        self.ct0 = self.ck.get("ct0", "")
        self.auth = self.ck.get("auth_token", "")
        if not (self.ct0 and self.auth):
            raise ValueError("cookie 必须含 auth_token 和 ct0")

    def headers(self, extra=None):
        return {
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "authorization": f"Bearer {BEARER}",
            "x-csrf-token": self.ct0,          # ★ 关键：ct0 必须同时在这里
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
            "Referer": "https://x.com/",
            "Origin": "https://x.com",
            "Cookie": f"auth_token={self.auth}; ct0={self.ct0}",
            **(extra or {}),
        }

    def graphql(self, doc_id, op_name, variables, features=None, timeout=30):
        url = (f"https://x.com/i/api/graphql/{doc_id}/{op_name}"
               f"?variables={urllib.parse.quote(json.dumps(variables, separators=(',', ':')))}")
        if features:
            url += f"&features={urllib.parse.quote(json.dumps(features, separators=(',', ':')))}"
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=self.headers()), timeout=timeout) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            body = e.read(800).decode("utf-8", "ignore")
            return e.code, {"_raw": body}
        except Exception as e:
            return 0, {"_err": f"{type(e).__name__}: {str(e)[:120]}"}


# 候选 doc_id（会随 X 更新变化；下面几个来自公开的 twscrape/网页快照）
DOC_IDS = {
    "UserByScreenName": ["32pL5BWe9WKeSK1MoPvFQQ", "G3KGOASz96M-Qu0nwmGXNg",
                         "sLVLhk0bGj3MVFEKTdax1w", "1VOOyvKkiI3FMmkeDNxM9A"],
    "UserTweets": ["V7H0Ap3_Hh2FyS75OCDO3Q", "E3opETHurmVJflFsUBVuUQ",
                   "HuTx74BxAnezK1gWvYY7zg", "QqZBEqganhHwmU9QssUirQ"],
}

USER_FEATURES = {
    "hidden_profile_subscriptions_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "subscriptions_verification_info_is_identity_verified_enabled": True,
    "subscriptions_verification_info_verified_since_enabled": True,
    "highlights_tweets_tab_ui_enabled": True,
    "responsive_web_twitter_article_notes_tab_enabled": True,
    "subscriptions_feature_can_gift_premium": True,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "responsive_web_graphql_timeline_navigation_enabled": True,
}

TWEET_FEATURES = {
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "responsive_web_grok_show_grok_translated_post": False,
    "responsive_web_grok_analysis_button_from_backend": True,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


def main():
    cs = os.environ.get("X_COOKIES", "").strip()
    if not cs:
        print("❌ 无 X_COOKIES")
        return 1
    cli = XClient(cs)
    print("=" * 60)
    print("自建 X 客户端实测")
    print("=" * 60)

    # 1) 找可用的 UserByScreenName doc_id
    print("\n--- 1) 探测 UserByScreenName doc_id ---")
    good = None
    for did in DOC_IDS["UserByScreenName"]:
        st, j = cli.graphql(did, "UserByScreenName",
                            {"screen_name": "sama", "withSafetyModeUserFields": True},
                            USER_FEATURES)
        err = ""
        if isinstance(j, dict) and "errors" in j:
            err = json.dumps(j["errors"])[:110]
        print(f"  doc_id={did:<24} HTTP {st} {err}")
        if st == 200 and "errors" not in j:
            good = did
            print("     ★★ 有效 ★★")
            break
    if not good:
        print("\n  ❌ 所有候选 doc_id 都不可用 → 需要从 x.com 网页里现抓 doc_id")
        # 尝试从网页 bundle 里提取
        print("\n--- 尝试从 x.com 网页提取最新 doc_id ---")
        try:
            with urllib.request.urlopen(urllib.request.Request(
                    "https://x.com/sama", headers=cli.headers()), timeout=30) as r:
                html = r.read(900000).decode("utf-8", "ignore")
            for op in ["UserByScreenName", "UserTweets"]:
                m = re.findall(r'"([A-Za-z0-9_-]{20,24})"\s*,\s*"' + op + r'"', html)
                if not m:
                    m = re.findall(op + r'"\s*,?\s*"?([A-Za-z0-9_-]{20,24})', html)
                print(f"   {op} 候选: {m[:5]}")
        except Exception as e:
            print(f"   取网页失败: {type(e).__name__}: {str(e)[:80]}")
        return 1

    # 2) 取用户 ID
    st, j = cli.graphql(good, "UserByScreenName",
                        {"screen_name": "sama", "withSafetyModeUserFields": True}, USER_FEATURES)
    uid = None
    try:
        uid = j["data"]["user"]["result"]["rest_id"]
        print(f"\n  ✅ 拿到 user id: {uid}   (name={j['data']['user']['result'].get('legacy',{}).get('name')})")
    except Exception:
        print(f"\n  ⚠️ 结构异常: {json.dumps(j)[:300]}")

    # 3) 探测 UserTweets doc_id
    if uid:
        print("\n--- 2) 探测 UserTweets doc_id ---")
        for did in DOC_IDS["UserTweets"]:
            st, j = cli.graphql(did, "UserTweets",
                                {"userId": uid, "count": 10, "includePromotedContent": True,
                                 "withQuickPromoteEligibilityTweetFields": True,
                                 "withVoice": True, "withV2Timeline": True},
                                TWEET_FEATURES)
            err = json.dumps(j.get("errors", []))[:110] if isinstance(j, dict) else ""
            print(f"  doc_id={did:<24} HTTP {st} {err}")
            if st == 200 and "errors" not in (j if isinstance(j, dict) else {}):
                print("     ★★ 有效 ★★")
                os.makedirs("data", exist_ok=True)
                with open("data/x_debug.json", "w", encoding="utf-8") as f:
                    json.dump({"uid": uid, "doc_id": did, "sample": j}, f,
                              ensure_ascii=False, indent=1)
                print("     样例已存 data/x_debug.json")
                break
    print("\n=== 结束 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
