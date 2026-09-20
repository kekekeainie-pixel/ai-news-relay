#!/usr/bin/env python3
"""dump X 原始响应结构，找出为什么某些账号解析出 0 条。"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from x_client import XClient, DOC_USER_TWEETS, TWEET_FEATURES, USER_FEATURES, DOC_USER_BY_SCREEN_NAME

cli = XClient(os.environ["X_COOKIES"])
for who in ["sama", "karpathy", "OpenAI"]:
    uid, name = cli.user_id(who)
    print(f"\n===== {who} uid={uid} name={name} =====")
    st, j = cli.graphql(DOC_USER_TWEETS, "UserTweets",
                        {"userId": str(uid), "count": 20, "includePromotedContent": True,
                         "withQuickPromoteEligibilityTweetFields": True,
                         "withVoice": True, "withV2Timeline": True}, TWEET_FEATURES)
    print("HTTP", st)
    if st != 200:
        print(json.dumps(j)[:400]); continue
    try:
        res = j["data"]["user"]["result"]
        print("result keys:", list(res.keys()))
        tl = res.get("timeline_v2") or res.get("timeline")
        print("timeline keys:", list(tl.keys()) if tl else "无")
        ins = tl["timeline"]["instructions"] if tl else []
        print("instructions types:", [list(x.keys()) for x in ins])
        for x in ins:
            ents = x.get("entries")
            if ents:
                print(f"  entries={len(ents)}, 前3个 entryId:")
                for e in ents[:3]:
                    c = e.get("content", {})
                    print("    ", e.get("entryId"), "| contentType:", c.get("entryType"), "| keys:", list(c.keys())[:6])
    except Exception as ex:
        print("解析异常:", type(ex).__name__, ex)
        print(json.dumps(j)[:600])
