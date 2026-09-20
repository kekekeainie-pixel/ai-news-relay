#!/usr/bin/env python3
"""验证一批 X 账号名是否存在，并取 uid + 粉丝数 —— 用于扩充抓取名单。
只读操作，不会关注/点赞/发推。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from x_client import XClient, DOC_USER_BY_SCREEN_NAME, USER_FEATURES

CANDIDATES = [
    # 复查可疑（上次结果里粉丝数异常或名字不符）
    "AnthropicAI", "xai", "sst", "opencode_ai", "opencode", "GroqInc", "Groq",
    "TheDecoder", "TLDRai", "TLDR_ai", "SyncedAI", "SyncedReview",
    "MetaAI", "AIatMeta", "CohereForAI", "cohere",
    "LangChainAI", "LangChain", "QbitAI", "QbitAI_", "量子位",
    # 补充候选
    "MSFTResearch", "MicrosoftAI", "NousResearch", "Alibaba_Qwen", "QwenLM",
    "zhipu_ai", "ZhipuAI", "MiniMax_AI", "MiniMaxAI", "MoonshotAI", "kimi_moonshot",
    "deepseek_ai", "DeepSeekAI", "ByteDance", "Baidu_Inc", "TencentAI",
    "AnthropicNews", "claudeai", "ClaudeDevs",
    "sama", "gdb", "ID_AA_Carmack",
    "TheStalwart", "EMostaque", "hardmaru", "BlancheMinerva",
    "Blaine_AI", "TheAIObserver", "aiindex", "AI_News_",
    "OpenAINewsroom", "OpenAIResearch",
    "Apple", "AppleML", "awscloud", "Azure", "googlecloud",
    "vercel", "supabase", "github", "huggingface",
    "PyTorch", "TensorFlow", "Keras_io", "pytorch",
    "ClementDelangue", "julien_c", "Thom_Wolf",
]


def main():
    cs = os.environ.get("X_COOKIES", "").strip()
    if not cs:
        print("❌ 无 X_COOKIES")
        return 1
    cli = XClient(cs)
    ok, bad = [], []
    print("=" * 68)
    print(f"验证 {len(CANDIDATES)} 个账号名")
    print("=" * 68)
    for h in CANDIDATES:
        st, j = cli.graphql(DOC_USER_BY_SCREEN_NAME, "UserByScreenName",
                            {"screen_name": h, "withSafetyModeUserFields": True},
                            USER_FEATURES)
        if st == 200:
            try:
                res = j["data"]["user"]["result"]
                uid = res["rest_id"]
                lg = res.get("legacy", {}) or {}
                name = lg.get("name", "")
                fc = lg.get("followers_count", 0)
                desc = (lg.get("description", "") or "").replace("\n", " ")[:60]
                ok.append({"handle": h, "uid": uid, "name": name,
                           "followers": fc, "desc": desc})
                print(f"  ✅ @{h:<18} {fc:>10,} 粉  {name[:28]}")
            except Exception as e:
                bad.append(h)
                print(f"  ⚠️ @{h:<18} 结构异常 {str(e)[:40]}")
        else:
            bad.append(h)
            print(f"  ❌ @{h:<18} HTTP{st}")
        time.sleep(1.1)

    print("\n" + "=" * 68)
    print(f"有效 {len(ok)} / 无效 {len(bad)}")
    print("=" * 68)
    print("无效的:", ", ".join(bad))
    # 按粉丝数排序输出，方便挑选
    ok.sort(key=lambda x: -x["followers"])
    print("\n有效账号（按粉丝数）:")
    for o in ok:
        print(f"  @{o['handle']:<18} {o['followers']:>10,}  {o['name'][:30]}")
    os.makedirs("data", exist_ok=True)
    with open("data/handles.json", "w", encoding="utf-8") as f:
        json.dump(ok, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
