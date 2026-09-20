#!/usr/bin/env python3
"""验证腾讯系 AI 官号候选。只读。"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from x_client import XClient, DOC_USER_BY_SCREEN_NAME, USER_FEATURES

CANDIDATES = [
    # 腾讯混元（Hunyuan / HY）
    "TencentHunyuan", "TencentHY", "Tencent_Hunyuan", "HunyuanAI", "hunyuan",
    "TencentAI", "TencentAI_Lab", "Tencent_AI", "Tencent",
    # CodeBuddy / WorkBuddy（同一团队）
    "CodeBuddy", "codebuddy_ai", "CodeBuddyAI", "TencentCodeBuddy",
    "WorkBuddy", "workbuddy_ai", "WorkBuddyAI", "TencentWorkBuddy",
    # 其他腾讯 AI 线
    "TencentCloud", "TencentCloudAI", "tencentcloud",
    "Tencent_Global", "TencentGlobal",
    # 补充可能（混元 3D / 元宝）
    "Hunyuan3D", "TencentYuanbao", "yuanbao_ai",
]


def main():
    cs = os.environ.get("X_COOKIES", "").strip()
    if not cs:
        print("❌ 无 X_COOKIES")
        return 1
    cli = XClient(cs)
    print("=" * 78)
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
                sc = lg.get("statuses_count", 0)
                ds = (lg.get("description", "") or "").replace("\n", " ")[:100]
                print(f"@{h:<20} {fc:>9,}粉 {'V' if v else ' '} 帖{sc:>6}  {nm[:22]}")
                if ds:
                    print(f"     bio: {ds}")
            except Exception as e:
                print(f"@{h:<20} WARN {str(e)[:40]}")
        else:
            print(f"@{h:<20} DEAD HTTP{st}")
        time.sleep(1.3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
