#!/usr/bin/env python3
"""
自建 X 客户端 —— 不依赖 twscrape（它的 doc_id 已过期）。

★ 关键（2026-09-20 实测得出）：
  cookie 里的 `ct0` 必须**同时**作为 `x-csrf-token` 请求头发送，
  否则 GraphQL 返回 403 code=353 "requires a matching csrf cookie and header"。
  官方 API v2 无 key → 401（必须付费，放弃）。
  syndication 嵌入接口对数据中心 IP 返回 429。

可用 doc_id（2026-09-20 实测）：
  UserByScreenName = 32pL5BWe9WKeSK1MoPvFQQ
  UserTweets       = V7H0Ap3_Hh2FyS75OCDO3Q

用法：
  X_COOKIES='auth_token=...; ct0=...' python scripts/x_client.py           # 自测
  X_COOKIES=... python scripts/x_client.py --out data/x.json --hours 48     # 供 relay 调用
"""
import argparse
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

DOC_USER_BY_SCREEN_NAME = "32pL5BWe9WKeSK1MoPvFQQ"
DOC_USER_TWEETS = "V7H0Ap3_Hh2FyS75OCDO3Q"

# ============================================================
# ★ 抓取名单（主人 2026-09-20 定稿）
#    原则①：大厂只留「最全的那个官方号」，不堆重叠号
#    原则②：全部经 verify_handles.py / verify_news_accounts.py 实测验真
#    剔除的同名高仿号（粉丝数暴露）：@xai(0) @tibo_maker(不是OpenAI那个Tibo!)
#    @TheDecoder(13) @TLDRai(59) @zhipu_ai(97) @MoonshotAI(145) @TencentAI(5)
#    @MetaAI(1万,真号@AIatMeta) @TheAIObserver(57) @AIExplained(187)
#    @model_behavior(661) @chrisolah(58) @ImportAI(65) @MehdiHassan(168)
#    @CohereForAI(198) @haiper_ai(0) @QbitAI/@量子位/@QwenLM/@ByteDance 不存在
# ============================================================

# ① 官方号（每个厂商只留最全的一个）
X_OFFICIAL = [
    "OpenAI",          # ★ 御三家：产品+研究+政策全在这发
    "AnthropicAI",     # ★
    "GoogleDeepMind",  # ★
    "grok",            # xAI（@xai 是 0 粉假号）
    "AIatMeta",        # Meta
    "MistralAI",       # 欧洲开源
    "huggingface",     # 开源社区中枢
    "NousResearch",    # 开源模型
    "deepseek_ai",     # ★ 国内
    "Alibaba_Qwen",    # ★ 国内
    "kimi_moonshot",   # ★ 国内
    "MiniMax_AI",      # ★ 国内
    "Zai_org",         # ★ 国内：智谱（海外品牌 Z.ai 的官方号，16.1万粉 1252帖）
    "Baidu_Inc",       # 国内：百度
    "TencentHunyuan",  # ★ 国内：腾讯混元（5.2万粉 782帖，真官号）
    "cursor_ai",       # 工具
    "opencode",        # 工具
    "commandcodeai",   # 工具
]

# ② 核心大佬 / 研究者
X_KOLS = [
    "elonmusk", "sama", "RayDalio",
    "karpathy", "gdb", "ID_AA_Carmack",
    "demishassabis", "sundarpichai", "JeffDean",
    "ylecun", "AndrewYNg", "drfeifei", "geoffreyhinton", "ilyasut", "simonw",
    "DrJimFan", "natolambert",
]

# ③ 快讯 / 额度重置 / 员工线人（第一时间发 AI 消息）
X_MEDIA = [
    "thsottiaux",      # ★★ OpenAI 的 Tibo —— 天天宣布 Codex 额度重置
    "lydiahallie",     # ★ Claude 侧「赛博义母」，也发重置
    "TheRundownAI", "rowancheung", "_akhaliq", "arankomatsuzaki",
    "rohanpaul_ai", "dair_ai", "TheTuringPost", "Yuchenj_UW",
    "teortaxesTex", "karminski3", "bcherny", "steipete",
]

# ★ 默认抓取名单
X_DEFAULT = X_OFFICIAL + X_KOLS + X_MEDIA

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


def parse_cookies(v):
    return dict(x.strip().split("=", 1) for x in v.split(";") if "=" in x)


class XClient:
    def __init__(self, cookies_str, timeout=30):
        self.ck = parse_cookies(cookies_str)
        self.ct0 = self.ck.get("ct0", "")
        self.auth = self.ck.get("auth_token", "")
        self.timeout = timeout
        if not (self.ct0 and self.auth):
            raise ValueError("cookie 必须含 auth_token 和 ct0")
        # ★ uid 缓存：UserByScreenName 每个账号要花 1 次请求额度，
        #   缓存后可省一半请求（限流约 50/窗口 → 从 25 个账号变 50 个）
        self._uid_cache = {}
        self._cache_path = os.environ.get("X_UID_CACHE", "data/x_uid_cache.json")
        try:
            if os.path.exists(self._cache_path):
                with open(self._cache_path, encoding="utf-8") as f:
                    self._uid_cache = json.load(f)
        except Exception:
            self._uid_cache = {}

    def save_uid_cache(self):
        try:
            os.makedirs(os.path.dirname(self._cache_path) or ".", exist_ok=True)
            with open(self._cache_path, "w", encoding="utf-8") as f:
                json.dump(self._uid_cache, f, ensure_ascii=False, indent=1)
        except Exception:
            pass

    def headers(self):
        return {
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "authorization": f"Bearer {BEARER}",
            "x-csrf-token": self.ct0,          # ★ 命门：ct0 必须同时在这里
            "x-twitter-active-user": "yes",
            "x-twitter-auth-type": "OAuth2Session",
            "x-twitter-client-language": "en",
            "Referer": "https://x.com/",
            "Origin": "https://x.com",
            "Cookie": f"auth_token={self.auth}; ct0={self.ct0}",
        }

    def graphql(self, doc_id, op, variables, features=None):
        url = (f"https://x.com/i/api/graphql/{doc_id}/{op}"
               f"?variables={urllib.parse.quote(json.dumps(variables, separators=(',', ':')))}")
        if features:
            url += f"&features={urllib.parse.quote(json.dumps(features, separators=(',', ':')))}"
        try:
            with urllib.request.urlopen(
                    urllib.request.Request(url, headers=self.headers()),
                    timeout=self.timeout) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read(700).decode("utf-8", "ignore")
            return e.code, {"_raw": raw}
        except Exception as e:
            return 0, {"_err": f"{type(e).__name__}: {str(e)[:110]}"}

    def user_id(self, screen_name):
        # ★ 命中缓存就不花请求额度
        ck = self._uid_cache.get(screen_name)
        if ck and ck.get("uid"):
            return ck["uid"], ck.get("name", "")
        st, j = self.graphql(DOC_USER_BY_SCREEN_NAME, "UserByScreenName",
                             {"screen_name": screen_name,
                              "withSafetyModeUserFields": True}, USER_FEATURES)
        if st != 200:
            return None, f"HTTP{st} {j.get('_raw','')[:80]}"
        try:
            res = j["data"]["user"]["result"]
            uid = res["rest_id"]
            nm = res.get("legacy", {}).get("name", "")
            self._uid_cache[screen_name] = {"uid": uid, "name": nm}
            return uid, nm
        except Exception:
            return None, f"结构异常 {json.dumps(j)[:100]}"

    def user_tweets(self, uid, limit=20):
        st, j = self.graphql(DOC_USER_TWEETS, "UserTweets",
                             {"userId": str(uid), "count": limit,
                              "includePromotedContent": True,
                              "withQuickPromoteEligibilityTweetFields": True,
                              "withVoice": True, "withV2Timeline": True},
                             TWEET_FEATURES)
        if st != 200:
            return [], f"HTTP{st} {j.get('_raw','')[:80]}"
        return parse_timeline(j), ""


def parse_timeline(j):
    """从 UserTweets 响应里抽出推文。兼容 note_tweet / retweet / quote 等形态。"""
    out = []
    try:
        instructions = (j["data"]["user"]["result"]["timeline_v2"]["timeline"]
                        ["instructions"])
    except Exception:
        # 备用路径（有些账号用 timeline）
        try:
            instructions = (j["data"]["user"]["result"]["timeline"]["timeline"]
                            ["instructions"])
        except Exception:
            return out
    for ins in instructions:
        for e in ins.get("entries", []) or []:
            c = e.get("content", {}) or {}
            item = c.get("itemContent") or {}
            tr = (item.get("tweet_results") or {}).get("result") or {}
            if not tr:
                continue
            tw = unwrap(tr)
            if not tw:
                continue
            lg = tw.get("legacy", {}) or {}
            text = lg.get("full_text") or ""
            # 长推文
            note = ((tw.get("note_tweet") or {}).get("note_tweet_results") or {}) \
                .get("result", {}).get("text")
            if note:
                text = note
            if not text:
                continue
            created = lg.get("created_at") or ""
            ts = 0
            if created:
                try:
                    ts = datetime.strptime(created, "%a %b %d %H:%M:%S %z %Y").timestamp()
                except Exception:
                    ts = 0
            tid = tw.get("rest_id") or lg.get("id_str") or ""
            screen = ((tw.get("core") or {}).get("user_results") or {}) \
                .get("result", {}).get("legacy", {}).get("screen_name") \
                or lg.get("user_id_str", "")
            out.append({"id": tid, "text": text, "ts": ts, "user": screen,
                        "url": f"https://x.com/{screen or 'i'}/status/{tid}" if tid else "",
                        "retweet": bool(lg.get("retweeted_status_result")),
                        "quote": bool(lg.get("quoted_status_result"))})
    return out


def unwrap(tr):
    """处理 TweetWithVisibilityResults / Tweet 两种包装。"""
    if not isinstance(tr, dict):
        return None
    if tr.get("__typename") == "TweetWithVisibilityResults":
        tr = tr.get("tweet", {}) or {}
    return tr if tr.get("legacy") or tr.get("rest_id") else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/x_debug.json")
    ap.add_argument("--hours", type=int, default=0, help="0=不过滤时间")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--users", default="", help="逗号分隔，覆盖默认名单")
    ap.add_argument("--group", default="default", choices=["default", "official", "kols", "media", "all"],
                    help="默认 default=官方+大佬；all=全部含媒体")
    a = ap.parse_args()

    cs = os.environ.get("X_COOKIES", "").strip()
    if not cs:
        print("❌ 无 X_COOKIES")
        return 1
    cli = XClient(cs)
    if a.users:
        users = [u.strip() for u in a.users.split(",") if u.strip()]
    elif a.group == "official":
        users = X_OFFICIAL
    elif a.group == "kols":
        users = X_KOLS
    elif a.group == "media":
        users = X_MEDIA
    elif a.group == "all":
        users = X_OFFICIAL + X_KOLS + X_MEDIA
    else:
        users = X_DEFAULT
    print("=" * 60)
    print(f"X 抓取：{len(users)} 个账号 (group={a.group})")
    print("=" * 60)

    # ★ 限流处理：X 对 cookie 账号约有「50 次/窗口」上限。
    #   策略：连续 3 次 429 就停止本轮（保留已抓到的），下次 cron 从断点继续。
    rate_limited_at = None
    consec_429 = 0
    all_items, stats = [], []
    for idx, u in enumerate(users):
        if rate_limited_at is None and consec_429 >= 3:
            rate_limited_at = idx
            print(f"  ⚠️ 连续 3 次 429，本轮在 [{u}] 处停止（已抓 {len(all_items)} 条）")
            break
        t0 = time.time()
        uid, note = cli.user_id(u)
        if not uid:
            if "429" in str(note):
                consec_429 += 1
                print(f"  [{u}] 429 限流 (第{consec_429}次连续)")
                stats.append({"user": u, "count": 0, "err": "429"})
                time.sleep(3.0)
            else:
                consec_429 = 0
                print(f"  [{u}] ✗ {note}")
                stats.append({"user": u, "count": 0, "err": note})
            continue
        consec_429 = 0
        tws, err = cli.user_tweets(uid, a.limit)
        if err:
            if "429" in str(err):
                consec_429 += 1
                print(f"  [{u}] 429 限流 (第{consec_429}次连续)")
                stats.append({"user": u, "count": 0, "err": "429"})
                time.sleep(3.0)
                continue
            print(f"  [{u}] ✗ {err}")
            stats.append({"user": u, "count": 0, "err": err})
            continue
        n = 0
        for t in tws:
            if a.hours and t["ts"] and t["ts"] < time.time() - a.hours * 3600:
                continue
            all_items.append({"source": f"X @{u}", "title": t["text"].replace("\n", " ")[:250],
                              "url": t["url"], "ts": int(t["ts"]),
                              "desc": t["text"][:400]})
            n += 1
        print(f"  [{u}] ✅ {n} 条 ({time.time()-t0:.1f}s) uid={uid}")
        stats.append({"user": u, "count": n, "err": ""})
        time.sleep(1.5)   # 温和点，别触发限流

    cli.save_uid_cache()   # ★ 保存 uid 缓存，下轮省掉 UserByScreenName 请求
    if all_items and a.out:
        os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as f:
            json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                       "count": len(all_items), "stats": stats,
                       "items": all_items}, f, ensure_ascii=False, indent=1)
        print(f"\n=== 共 {len(all_items)} 条 → {a.out} ===")
        for it in all_items[:6]:
            dt = datetime.fromtimestamp(it["ts"], timezone.utc).strftime("%m-%d %H:%M") if it["ts"] else "?"
            print(f"   [{it['source']:<20}] {dt} {it['title'][:60]}")
    else:
        print(f"\n=== 0 条 ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
