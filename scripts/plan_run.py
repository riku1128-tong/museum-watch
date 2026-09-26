"""今日の巡回計画（各館を full / light / skip のどれで確認するか）をバッチに分けて JSON で出す。

    uv run scripts/plan_run.py              # 既定: 8 館ずつ
    uv run scripts/plan_run.py --batch 6 --only Q1234,Q5678 --mode full
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from common import CRAWL_PRIORITY, DETAILS, MUSEUMS_JSON, now_jst, read_json
from areas import area_of

FULL_EVERY_DAYS = 28  # 週 1 回の巡回では、4 週に 1 回だけ全体を読み直す
CLOSED_RECHECK_DAYS = 30


def decide(m: dict, det: dict | None, today) -> tuple[str, str]:
    if m["status"] == "closed":
        return "skip", "Wikidata 上で閉館"
    if det is None:
        return "full", "初回"
    age = (today - datetime.fromisoformat(det["checked_at"]).date()).days
    if det["operating_status"] == "permanently_closed":
        return ("light", "閉館の再確認") if age >= CLOSED_RECHECK_DAYS else ("skip", "閉館済み")
    if age == 0:
        return "skip", "今日確認済み"
    if "access" not in det or "adult_price" not in det:
        return "full", "料金・最寄駅が未取得"
    if not det.get("highlights"):
        return "full", "見どころが未作成"
    if age >= FULL_EVERY_DAYS:
        return "full", f"{age} 日前に確認"
    if det["confidence"] == "low" or det["operating_status"] == "unknown":
        return "full", "前回の情報が不確か"
    if not (det.get("official_url") or m.get("official_url")):
        return "full", "公式URL不明"
    last = datetime.fromisoformat(det["checked_at"]).date().isoformat()
    ended = [e["title"] for e in det["exhibitions"] if last <= e["end"] < today.isoformat()]
    if ended:
        return "full", f"展示終了: {ended[0]}"
    if not any(e["start"] <= today.isoformat() <= e["end"] for e in det["exhibitions"]):
        return "full", "開催中の展示が未登録"
    return "light", "差分確認"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--only", default="", help="カンマ区切りの id だけを対象にする")
    ap.add_argument("--mode", choices=["full", "light"], help="判定を無視してこのモードにする")
    ap.add_argument("--max-new", type=int, default=100,
                    help="まだ一度も巡回していない館を 1 回に何館まで読むか（観光地 → 関東 → 近い地域 → 都道府県コード順）")
    ap.add_argument("--retry", action="store_true",
                    help="今日確認したのに情報が不十分な館（時間が空・状態不明・confidence low）と未取得の館だけを 1 館ずつ返す")
    args = ap.parse_args()

    today = now_jst().date()
    only = {x for x in args.only.split(",") if x}
    items = []
    for m in read_json(MUSEUMS_JSON)["museums"]:
        if only and m["id"] not in only:
            continue
        path = DETAILS / f"{m['id']}.json"
        det = read_json(path) if path.exists() else None
        mode, why = decide(m, det, today)
        if args.retry:
            if m["status"] == "closed" or (det and det["operating_status"] in ("permanently_closed", "temporarily_closed")):
                continue
            weak = (det is None or det["confidence"] == "low" or det["operating_status"] == "unknown"
                    or (det["operating_status"] == "operating" and not det["regular_hours"]))
            if not weak:
                continue
            mode, why = "full", "再挑戦"
        elif args.mode and (only or mode != "skip"):
            mode, why = args.mode, "指定"
        items.append({"id": m["id"], "name": m["name"], "prefecture": m["prefecture"],
                      "official_url": (det or {}).get("official_url") or m.get("official_url"),
                      "wiki_title": m["wiki_title"], "mode": mode, "why": why,
                      "detail_path": f"data/details/{m['id']}.json"})

    # 初回の館は 1 回あたり max_new 館まで。残りは次回以降に回す。観光地（areas.AREAS）の館を先に読む（宿の紹介につながるため）
    in_area = {m["id"] for m in read_json(MUSEUMS_JSON)["museums"] if area_of(m)}
    fresh = sorted((i for i in items if i["why"] == "初回"),
                   key=lambda i: (i["id"] not in in_area, CRAWL_PRIORITY.index(i["prefecture"])))
    for i in fresh[args.max_new:]:
        i["mode"], i["why"] = "skip", "順番待ち"

    todo = [i for i in items if i["mode"] != "skip"]
    # full を先に並べ、各バッチに full が偏らないよう交互に配る
    todo.sort(key=lambda i: i["mode"] != "full")
    n = len(todo) if args.retry else max(1, -(-len(todo) // args.batch))
    batches = [todo[k::n] for k in range(n)] if todo else []
    print(json.dumps({
        "date": today.isoformat(),
        "counts": {k: sum(1 for i in items if i["mode"] == k) for k in ("full", "light", "skip")},
        "batches": batches,
        "waiting": sum(1 for i in items if i["why"] == "順番待ち"),
        "skipped": [{"id": i["id"], "name": i["name"], "why": i["why"]} for i in items
                    if i["mode"] == "skip" and i["why"] != "順番待ち"],
    }, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
