"""data/details/*.json をスキーマと整合性ルールで検証する。エラーがあれば終了コード 1。

    uv run scripts/validate.py              # 全館
    uv run scripts/validate.py Q1234 Q5678  # 指定した館だけ
"""

from __future__ import annotations

import sys

from jsonschema import Draft202012Validator

from common import DETAILS, MUSEUMS_JSON, SCHEMA, read_json
from render import specificity


def overlap_errors(hours: list[dict], label: str) -> list[str]:
    """同じ曜日に同じ具体度の時間定義が 2 つ以上あると、どれが正しいか決められないのでエラーにする。"""
    errs = []
    for i, a in enumerate(hours):
        for b in hours[i + 1:]:
            same = set(a["days"]) & set(b["days"])
            # 期間や対象曜日数が違えば render.py が「具体的な方を優先」で解決する。どちらも同じなら矛盾
            dates_overlap = ((a.get("from") or "0000") <= (b.get("to") or "9999")
                             and (b.get("from") or "0000") <= (a.get("to") or "9999"))
            if same and dates_overlap and specificity(a) == specificity(b):
                errs.append(f"{label}: {sorted(same)} の時間が重複 "
                            f"({a['open']}-{a['close']} と {b['open']}-{b['close']})。曜日ごとに 1 つにする")
    return errs


def semantic_errors(d: dict) -> list[str]:
    errs = []
    for e in d["exhibitions"]:
        if e["start"] > e["end"]:
            errs.append(f"展示「{e['title']}」の会期が逆転: {e['start']} > {e['end']}")
    for c in d["special_closures"]:
        if c["from"] > c["to"]:
            errs.append(f"臨時休館の期間が逆転: {c['from']} > {c['to']}")
    hours = list(d["regular_hours"]) + [h for e in d["exhibitions"] for h in e.get("hours", [])]
    for h in hours:
        if h["open"] >= h["close"]:
            errs.append(f"開館時刻が閉館時刻以降: {h['open']}-{h['close']}")
        if h.get("last_entry") and not (h["open"] <= h["last_entry"] <= h["close"]):
            errs.append(f"最終入館が開館時間外: {h['last_entry']}")
    errs += overlap_errors(d["regular_hours"], "regular_hours")
    for e in d["exhibitions"]:
        errs += overlap_errors(e.get("hours", []), f"展示「{e['title']}」の hours")
    if d["operating_status"] == "operating" and not d["regular_hours"] and d["confidence"] != "low":
        errs.append("営業中なのに regular_hours が空（読めなかったなら confidence を low に）")
    return errs


def main(ids: list[str]) -> int:
    validator = Draft202012Validator(read_json(SCHEMA))
    known = {m["id"] for m in read_json(MUSEUMS_JSON)["museums"]}
    files = [DETAILS / f"{i}.json" for i in ids] if ids else sorted(DETAILS.glob("*.json"))
    bad = 0
    for f in files:
        try:
            d = read_json(f)
        except Exception as ex:  # noqa: BLE001 - JSON 破損もそのまま報告する
            print(f"NG {f.name}: 読み込めない ({ex})")
            bad += 1
            continue
        errs = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
                for e in validator.iter_errors(d)]
        if not errs:
            if d["id"] != f.stem:
                errs.append(f"id ({d['id']}) がファイル名と違う")
            if d["id"] not in known:
                errs.append("museums.json に無い id")
            errs += semantic_errors(d)
        if errs:
            bad += 1
            print(f"NG {f.name}")
            for e in errs:
                print(f"   - {e}")
    print(f"{len(files) - bad}/{len(files)} 件 OK")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
