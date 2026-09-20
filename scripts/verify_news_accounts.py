#!/usr/bin/env python3
"""验证「AI 快讯猎手」候选账号 —— 只读，不关注/点赞/发推。"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from x_client import XClient, DOC_USER_BY_SCREEN_NAME, USER_FEATURES

CANDIDATES = [
    # ① 快讯型（第一时间发 AI 消息）
    "TheRundownAI", "rowancheung", "mreflow", "TheAIObserver", "ai_for_success",
    "TheTuringPost", "arankomatsuzaki", "rohanpaul_ai", "_akhaliq", "dair_ai",
    "askalphaxiv", "TheAhmadOsman", "EpochAIResearch", "TwoMinutePapers",
    "AIExplained", "kimmonismus", "teortaxesTex", "blizaine", "ns123abc",
    "Yuchenj_UW", "scaling01", "alexalbert__", "haiper_ai", "AIWarehouse",
    # ② 研究者（一手观点）
    "drfeifei", "geoffreyhinton", "ilyasut", "timnitGebru", "arthurmensch",
    "LiamFedus", "OriolVinyalsML", "model_behavior", "bcherny", "steipete",
    "schmidhuberAI", "yoshuabengio", "chelseabfinn", "svlevine", "pabbeel",
    "chrisolah", "janleike", "sarahookr", "mmitchell_ai", "DaphneKoller",
    # ③ 其他 AI 媒体 / 通讯
    "simonw", "fofrAI", "TheInformation", "ImportAI", "AInewsletter",
    "thezvi", "jackclarkSF", "AISafetyMemes", "MehdiHassan", "nathanbenaich",
    # ④ 官方补充
    "xai", "ThinkingMachines", "ssi", "SafeSuperintelligence",
    "Microsoft", "Google", "Meta", "AIatMeta", "CohereForAI",
    # ⑤ 中文圈
    "AiGuangBiao", "hqy_stone", "ZhuoZhuoCrayon", "lifan_zhao", "karminski3",
]


def main():
    cs = os.environ.get("X_COOKIES", "").strip()
    if not cs:
        print("❌ 无 X_COOKIES")
        return 1
    cli = XClient(cs)
    ok, bad = [], []
    print("=" * 68)
    print(f"验证 {len(CANDIDATES)} 个候选")
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
                fc = lg.get("followers_count", 0)
                nm = lg.get("name", "")
                v = lg.get("verified", False)
                ds = (lg.get("description", "") or "").replace("\n", " ")[:70]
                # 只保留看起来真实的（粉丝 > 1000）
                if fc >= 1000:
                    ok.append({"handle": h, "uid": uid, "name": nm,
                               "followers": fc, "verified": v, "desc": ds})
                    print(f"  OK   @{h:<20} {fc:>10,} {'V' if v else ' '} {nm[:24]}")
                else:
                    bad.append(h)
                    print(f"  LOW  @{h:<20} {fc:>10,}  粉丝太少, 疑似假号")
            except Exception as e:
                bad.append(h)
                print(f"  WARN @{h:<20} {str(e)[:40]}")
        else:
            bad.append(h)
            print(f"  DEAD @{h:<20} HTTP{st}")
        time.sleep(1.4)

    ok.sort(key=lambda x: -x["followers"])
    print("\n" + "=" * 68)
    print(f"有效 {len(ok)} / 剔除 {len(bad)}")
    print("=" * 68)
    for o in ok:
        print(f"  @{o['handle']:<20} {o['followers']:>10,}  {o['desc'][:52]}")
    os.makedirs("data", exist_ok=True)
    with open("data/handles_new.json", "w", encoding="utf-8") as f:
        json.dump(ok, f, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
