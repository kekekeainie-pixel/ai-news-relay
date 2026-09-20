#!/usr/bin/env python3
"""定向验证：智谱/Z.ai 海外官号 + 主人名单里还没验的 4 个号。只读。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from x_client import XClient, DOC_USER_BY_SCREEN_NAME, USER_FEATURES

CANDIDATES = [
    # 智谱 / Z.ai 海外官号候选
    "Zai_org", "zai", "ZaiOfficial", "Zai_AI", "GLM_Zai", "Z_ai",
    "ZhipuAI", "zhipu_ai", "ZhipuAI_", "Zhipu_zh", "zhipu",
    "chatglm", "ChatGLM", "GLM_AI",
    # 主人名单里未验的
    "thsottiaux", "lydiahallie", "Baidu_Inc",
]


def main():
    cs = os.environ.get("X_COOKIES", "").strip()
    if not cs:
        print("❌ 无 X_COOKIES")
        return 1
    cli = XClient(cs)
    print("=" * 76)
    for h in CANDIDATES:
        st, j = cli.graphql(DOC_USER_BY_SCREEN_NAME, "UserByScreenName",
                            {"screen_name": h, "withSafetyModeUserFields": True},
                            USER_FEATURES)
        if st == 200:
            try:
                res = j["data"]["user"]["result"]
                lg = res.get("legacy", {}) or {}
                fc = lg.get("followers_count", 0)
                nm = lg.get("name", "")
                v = lg.get("verified", False)
                ds = (lg.get("description", "") or "").replace("\n", " ")[:110]
                cr = lg.get("created_at", "")
                sc = lg.get("statuses_count", 0)
                print(f"@{h:<18} {fc:>9,}粉 {'✓V' if v else '  '} 帖{sc:>6}  {nm[:24]}")
                print(f"    bio: {ds}")
            except Exception as e:
                print(f"@{h:<18} WARN {str(e)[:40]}")
        else:
            print(f"@{h:<18} DEAD HTTP{st}")
        time.sleep(1.3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
