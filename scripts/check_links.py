"""アフィリエイトの提携先とお問い合わせフォームのリンクが生きているか確かめる。毎週の巡回の最後に実行する（手順書 4.5）。

    uv run scripts/check_links.py          # 有効（enabled: true）な提携先と、お問い合わせフォーム
    uv run scripts/check_links.py --all    # 無効の提携先も含める（提携前の URL の下調べ用）

提携先ごとに、置き場所ごとの見本の館・展覧会で URL を組み立てて開く。
HTTP 400 以上・接続できない・提携終了らしいページに転送された場合を NG とし、1 件でも NG があれば終了コード 1 を返す。
NG の提携先を自動で無効にはしない（収益に関わるので、報告を見て人が決める）。
"""

from __future__ import annotations

import argparse
import json
import sys

import requests

from affiliate import CONFIG, fill
from common import DETAILS, MUSEUMS_JSON, http, read_json
from contact import form_url

# 提携が終わったリンクは、エラーではなく案内ページに転送されることが多い
ENDED_WORDS = ["終了しました", "掲載を終了", "提携が解除", "プログラムは終了", "ページが見つかりません", "お探しのページ"]


def samples() -> tuple[dict, dict | None]:
    """URL の差し込みに使う見本（巡回済みで、開催中の展覧会がある館）。"""
    ms = [m for m in read_json(MUSEUMS_JSON)["museums"] if m["status"] != "closed" and (DETAILS / f"{m['id']}.json").exists()]
    for m in ms:
        exs = read_json(DETAILS / f"{m['id']}.json")["exhibitions"]
        if exs:
            return m, exs[0]
    return ms[0], None


def check(url: str, s: requests.Session) -> dict:
    try:
        r = s.get(url, timeout=20, allow_redirects=True)
    except requests.RequestException as e:
        return {"ok": False, "status": None, "why": type(e).__name__}
    text = r.text[:200_000] if "text/html" in r.headers.get("content-type", "") else ""
    ended = next((w for w in ENDED_WORDS if w in text), None)
    ok = r.status_code < 400 and not ended
    return {"ok": ok, "status": r.status_code, "final_url": r.url,
            **({"why": f"HTTP {r.status_code}" if r.status_code >= 400 else f"「{ended}」を含むページ"} if not ok else {})}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="無効の提携先も確かめる")
    args = ap.parse_args()

    partners = json.loads(CONFIG.read_text(encoding="utf-8")).get("partners", []) if CONFIG.exists() else []
    partners = [p for p in partners if args.all or p.get("enabled")]
    m, e = samples()
    s = http()
    # 提携先のサイトには普通のブラウザとして見せる（ボット向けの別ページを返すところがあるため）
    s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"

    results = []
    for p in partners:
        for placement in p.get("placements", []):
            url = fill(p["url"], m, e if placement == "exhibition" else None, placement)
            results.append({"target": f"{p['id']} / {placement}", "url": url} | check(url, s))
    if form_url():
        results.append({"target": "お問い合わせフォーム", "url": form_url()} | check(form_url(), s))

    ng = [r for r in results if not r["ok"]]
    print(json.dumps({"checked": len(results), "ng": ng}, ensure_ascii=False, indent=1))
    if not results:
        print("確かめるリンクがありません（有効な提携先もお問い合わせフォームも未設定）", file=sys.stderr)
    sys.exit(1 if ng else 0)


if __name__ == "__main__":
    main()
