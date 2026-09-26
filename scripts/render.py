"""詳細 JSON から日ごとの開館状況を決定的に計算し、docs/index.html と日次スナップショットを作る。

    uv run scripts/render.py                    # 今日から 14 日分
    uv run scripts/render.py --date 2026-12-29  # 指定日から（判定の確認用）
    uv run scripts/render.py --date 2026-10-12 --print   # 判定結果を表で出すだけ
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta

import jpholiday

from areas import place_name
from common import DATA, DAILY, DETAILS, MUSEUMS_JSON, PREFS, REGIONS, ROOT, SITE, now_jst, read_json, write_json

WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
STALE_DAYS = 8  # 巡回は毎週金曜。1 回ぶん遅れたら要確認にする
TEMPLATE = ROOT / "scripts" / "template.html"


def wd(d: date) -> str:
    return WEEKDAYS[d.weekday()]


def is_holiday(d: date) -> bool:
    return jpholiday.is_holiday(d)


def in_range(d: date, start: str | None, end: str | None) -> bool:
    s = d.isoformat()
    return (start is None or start <= s) and (end is None or s <= end)


def is_year_end(d: date) -> bool:
    return (d.month == 12 and d.day >= 28) or (d.month == 1 and d.day <= 3)


def nth_of_month(d: date) -> int:
    return (d.day - 1) // 7 + 1


def is_regular_closed_day(d: date, closed: set[str], nth: list[dict]) -> str | None:
    """曜日だけで見た定休日なら理由を返す（祝日かどうかは見ない）。"""
    if wd(d) in closed:
        return "定休日"
    for r in nth:
        if r["weekday"] == wd(d) and nth_of_month(d) in r["nth"]:
            return f"定休日（第{nth_of_month(d)}{'月火水木金土日'[d.weekday()]}曜）"
    return None


def closed_by_rule(d: date, closed: set[str], rule: str, nth: list[dict] = ()) -> tuple[bool, str | None]:
    """定休日（毎週・第n週）と祝日ルールによる休館判定。(休館か, 理由)"""
    if is_holiday(d):
        if "holiday" in closed or rule == "closed":
            return True, "祝日休館"
        if rule in ("open", "open_next_weekday_closed"):
            return False, None
        # rule unknown: 曜日だけで判定する
    elif rule == "open_next_weekday_closed" and d.weekday() < 5:
        # 定休日が祝日で開館した場合、その後の最初の平日（祝日でない月〜金）を振替休館にする
        p = d - timedelta(days=1)
        while is_holiday(p) or p.weekday() >= 5:
            if is_holiday(p) and is_regular_closed_day(p, closed, nth):
                return True, f"振替休館（{p.month}/{p.day} 祝日開館のため）"
            p -= timedelta(days=1)
    why = is_regular_closed_day(d, closed, nth)
    return (True, why) if why else (False, None)


def specificity(h: dict) -> tuple[int, int]:
    """小さいほど具体的。期間が狭い定義 → 対象曜日が少ない定義の順に優先する。"""
    lo = date.fromisoformat(h.get("from") or "1900-01-01")
    hi = date.fromisoformat(h.get("to") or "2999-12-31")
    return (hi - lo).days, len(h["days"])


def matching_hours(hours: list[dict], d: date) -> dict | None:
    # 「毎日18時まで」＋「金曜は20時まで」「12/7〜10は20時まで」のような上書きを具体的な方で解決する
    cands = sorted((h for h in hours if in_range(d, h.get("from"), h.get("to"))), key=specificity)
    if is_holiday(d):
        for h in cands:
            if "holiday" in h["days"]:
                return h
    return next((h for h in cands if wd(d) in h["days"]), None)


def parse_price(text: str | None) -> int | None:
    """「一般 2,300円」「大人 1,500円（日時指定）」「無料」から大人一般の料金を取り出す。"""
    if not text:
        return None
    m = re.search(r"(?:一般|大人)[^0-9無]{0,12}([0-9,]+)\s*円", text) or re.search(r"([0-9,]+)\s*円", text)
    if m:
        return int(m.group(1).replace(",", ""))
    return 0 if "無料" in text else None


def exhibition_price(e: dict) -> int | None:
    return e["adult_price"] if e.get("adult_price") is not None else parse_price(e.get("admission"))


def free_on(det: dict, d: date) -> dict | None:
    """大人一般が無料になる日なら {scope, reason[, targets]} を返す。館全体 → 常設のみ → 一部 の順に優先する。"""
    hits = [f for f in det.get("free_days", []) if in_range(d, f["from"], f["to"])]
    for r in det.get("free_rules", []):
        if r.get("day_of_month") == d.day or (
                r.get("weekday") == wd(d) and (not r.get("nth") or nth_of_month(d) in r["nth"])):
            hits.append(r)
    if not hits:
        return None
    best = min(hits, key=lambda f: ["all", "collection", "partial"].index(f["scope"]))
    out = {"scope": best["scope"], "reason": best.get("reason")}
    if best["scope"] == "partial":
        out["targets"] = sorted({t for f in hits if f["scope"] == "partial" for t in f.get("targets", [])})
    return out


def active_exhibitions(det: dict, d: date) -> list[dict]:
    out = []
    for e in det["exhibitions"]:
        if not in_range(d, e["start"], e["end"]) or d.isoformat() in e.get("closed_dates", []):
            continue
        if wd(d) in e.get("closed_weekdays", []) and not is_holiday(d):
            continue
        h = matching_hours(e.get("hours", []), d)
        out.append({"title": e["title"], "start": e["start"], "end": e["end"], "url": e.get("url"),
                    "kind": e.get("kind", "other"), "summary": e.get("summary"),
                    "admission": e.get("admission"), "price": exhibition_price(e),
                    "open": h["open"] if h else None, "close": h["close"] if h else None})
    # 企画展を先に、会期末が近い順
    return sorted(out, key=lambda x: (x["kind"] != "special", x["end"]))


def upcoming_exhibitions(det: dict, d: date, within: int = 14) -> list[dict]:
    limit = (d + timedelta(days=within)).isoformat()
    return [{"title": e["title"], "start": e["start"], "end": e["end"], "url": e.get("url")}
            for e in det["exhibitions"] if d.isoformat() < e["start"] <= limit]


def judge(m: dict, det: dict | None, d: date, today: date) -> dict:
    """1 館 1 日分の判定。status は open / closed / unknown。"""
    base = {"id": m["id"], "status": "unknown", "reason": None, "open": None, "close": None,
            "last_entry": None, "exhibitions": [], "upcoming": [], "needs_check": True}
    if det is None:
        # まだ一度も巡回していない館（全国対応で順番に巡回中）
        return base | {"status": "pending", "reason": "情報準備中", "needs_check": False}

    checked = datetime.fromisoformat(det["checked_at"]).date()
    needs_check = det["confidence"] == "low" or (today - checked).days >= STALE_DAYS
    # 無料開放は休館日にも表示する（例: 建物は展示替えで休館でも、庭園だけ無料公開）
    base |= {"needs_check": needs_check, "exhibitions": active_exhibitions(det, d),
             "upcoming": upcoming_exhibitions(det, d), "free": free_on(det, d)}

    if det["operating_status"] == "temporarily_closed":
        return base | {"status": "closed", "reason": det.get("status_note") or "長期休館中"}
    if det["operating_status"] == "unknown":
        return base | {"reason": det.get("status_note") or "営業状況不明"}

    for c in det["special_closures"]:
        if in_range(d, c["from"], c["to"]):
            return base | {"status": "closed", "reason": c.get("reason") or "臨時休館"}

    special = next((o for o in det["special_openings"] if o["date"] == d.isoformat()), None)
    if special is None:
        if det["holiday_rule"] == "unknown" and is_holiday(d):
            base["needs_check"] = True
        if is_year_end(d) and not any(is_year_end(date.fromisoformat(c["from"])) or is_year_end(date.fromisoformat(c["to"]))
                                      for c in det["special_closures"]):
            base["needs_check"] = True  # 年末年始の休館情報がまだ取れていない
        closed, why = closed_by_rule(d, set(det["closed_weekdays"]), det["holiday_rule"],
                                     det.get("closed_nth_weekdays", []))
        if closed:
            return base | {"status": "closed", "reason": why}
        if det.get("closed_between_exhibitions") and det["exhibitions"] and not base["exhibitions"]:
            return base | {"status": "closed", "reason": "展示替え期間"}

    h = matching_hours(det["regular_hours"], d)
    opens = [x for x in [special and special.get("open"), h and h["open"]] if x]
    closes = [x for x in [special and special.get("close"), h and h["close"]] if x]
    # 展覧会独自の時間があれば、館としてはいちばん早い開館〜いちばん遅い閉館で示す
    opens += [e["open"] for e in base["exhibitions"] if e["open"]]
    closes += [e["close"] for e in base["exhibitions"] if e["close"]]
    if not opens and not det["regular_hours"]:
        return base | {"reason": "開館時間が読み取れていない"}
    return base | {
        "status": "open",
        "reason": special.get("note") if special else None,
        "open": min(opens) if opens else None,
        "close": max(closes) if closes else None,
        "last_entry": h.get("last_entry") if h else None,
        "needs_check": base["needs_check"] or not opens,
    }


def load_details() -> dict[str, dict]:
    return {f.stem: read_json(f) for f in DETAILS.glob("*.json")}


def museum_price(det: dict | None) -> int | None:
    """館の大人一般料金。未取得なら常設・コレクション展の料金で代用する。"""
    if not det:
        return None
    if det.get("adult_price") is not None:
        return det["adult_price"]
    prices = [p for e in det["exhibitions"] if e.get("kind") == "collection" and (p := exhibition_price(e)) is not None]
    return min(prices) if prices else None


def museum_meta(m: dict, det: dict | None) -> dict:
    return {
        "id": m["id"], "name": m["name"], "category": m["category"], "prefecture": m["prefecture"],
        "municipality": m.get("municipality"),
        "place": place_name(m),  # 宿の検索（アフィリエイト）に使う地名
        "url": (det or {}).get("official_url") or m.get("official_url"),
        "address": (det or {}).get("address"),
        "wiki": f"https://ja.wikipedia.org/wiki/{m['wiki_title']}",
        "lat": m.get("lat"), "lng": m.get("lng"),
        "price": museum_price(det),
        "access": (det or {}).get("access", []),
        # 展覧会は館ごとに 1 回だけ持ち、日ごとの結果からは番号で参照する（ページを軽くするため）
        "exhibitions": [{k: v for k, v in {
            "title": e["title"], "start": e["start"], "end": e["end"], "url": e.get("url"), "kind": e.get("kind", "other"),
            "summary": e.get("summary"), "admission": e.get("admission"), "price": exhibition_price(e)}.items() if v is not None}
            for e in (det or {}).get("exhibitions", [])],
        "checked_at": (det or {}).get("checked_at"),
    }


def compact(result: dict, meta: dict) -> dict:
    """日ごとの判定結果を HTML 埋め込み用に縮める。展覧会は館の一覧の番号にし、空の値は省く（ページ側で元に戻す）。"""
    index = {(e["title"], e["start"]): i for i, e in enumerate(meta["exhibitions"])}
    out = {k: v for k, v in result.items() if v not in (None, False, [], {}) and k not in ("exhibitions", "upcoming")}
    if result["exhibitions"]:
        out["exhibitions"] = [[index[(e["title"], e["start"])], e["open"], e["close"]] for e in result["exhibitions"]]
    if result["upcoming"]:
        out["upcoming"] = [index[(e["title"], e["start"])] for e in result["upcoming"]]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat, default=None)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--print", action="store_true", help="HTML を書かず、指定日の判定を表示する")
    ap.add_argument("--log", action="store_true", help="data/run_log.jsonl に巡回結果を 1 行追記する")
    ap.add_argument("--failed", default="", help="--log 用: 取得に失敗した館の id（カンマ区切り）")
    ap.add_argument("--started", default=None, help="--log 用: 巡回開始時刻 (ISO)")
    ap.add_argument("--weekly-before", type=int, default=None, help="--log 用: 巡回前のプラン週次使用率 (%%)")
    ap.add_argument("--weekly-after", type=int, default=None, help="--log 用: 巡回後のプラン週次使用率 (%%)")
    args = ap.parse_args()

    today = now_jst().date()
    start = args.date or today
    master = read_json(MUSEUMS_JSON)["museums"]
    details = load_details()

    active, gone = [], []
    for m in master:
        det = details.get(m["id"])
        if m["status"] == "closed" or (det and det["operating_status"] == "permanently_closed"):
            gone.append({"name": m["name"], "note": (det or {}).get("status_note") or m.get("closed_on")})
        else:
            active.append(m)

    days = []
    for i in range(args.days):
        d = start + timedelta(days=i)
        days.append({
            "date": d.isoformat(), "weekday": "月火水木金土日"[d.weekday()],
            "holiday": jpholiday.is_holiday_name(d),
            "results": [judge(m, details.get(m["id"]), d, today) for m in active],
        })

    if args.print:
        d0 = days[0]
        print(f"{d0['date']}（{d0['weekday']}）{d0['holiday'] or ''}")
        names = {m["id"]: m["name"] for m in active}
        for r in sorted(d0["results"], key=lambda r: r["status"]):
            hrs = f"{r['open']}-{r['close']}" if r["open"] else ""
            ex = " / ".join(e["title"] for e in r["exhibitions"][:2])
            flag = " ⚠" if r["needs_check"] else ""
            print(f"  [{r['status']:7}] {names[r['id']]} {hrs} {r['reason'] or ''}{flag}  {ex}")
        return

    metas = {m["id"]: museum_meta(m, details.get(m["id"])) for m in active}
    payload = {
        "generated_at": now_jst().isoformat(timespec="minutes"),
        "museums": metas,
        "gone": gone,
        "regions": {r: [p for p in ps if any(m["prefecture"] == p for m in active)] for r, ps in REGIONS.items()},
        "pref_codes": {p: f"{i + 1:02d}" for i, p in enumerate(PREFS)},
        "affiliates": __import__("affiliate").for_js(),  # 「行き方」シートの広告枠（有効な提携先だけ）
        # 準備中の館は毎日同じなので日ごとには持たず、ページ側で各日に足す
        "pending": [m["id"] for m in active if m["id"] not in details],
        "days": [{**d, "results": [compact(r, metas[r["id"]]) for r in d["results"] if r["status"] != "pending"]}
                 for d in days],
    }
    write_json(DAILY / f"{start.isoformat()}.json", {"generated_at": payload["generated_at"], **days[0]})

    from pages import ga_snippet
    html = TEMPLATE.read_text(encoding="utf-8").replace("<!--__GA__-->", ga_snippet()).replace(
        "/*__DATA__*/null", json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))
    SITE.mkdir(exist_ok=True)
    (SITE / "index.html").write_text(html, encoding="utf-8")
    (SITE / "style.css").write_text((ROOT / "scripts" / "style.css").read_text(encoding="utf-8"), encoding="utf-8")
    # ホーム画面に追加してアプリのように使うための設定（PWA）。Service Worker は生成のたびに版を変えて古いキャッシュを捨てる
    write_json(SITE / "manifest.webmanifest", {
        "name": "美術館ウォッチ", "short_name": "美術館ウォッチ", "lang": "ja",
        "description": "全国の美術館の開館状況・開館時間・料金・開催中の展覧会",
        "start_url": "./", "scope": "./", "display": "standalone",
        "background_color": "#141312", "theme_color": "#141312",
        "icons": [{"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
    })
    (SITE / "sw.js").write_text((ROOT / "scripts" / "sw.js").read_text(encoding="utf-8")
                                .replace("__VERSION__", payload["generated_at"].replace(":", "")), encoding="utf-8")

    # 検索から人が来るための静的ページ（館・展覧会・都道府県）と sitemap.xml
    import pages
    n_pages = pages.build(active, details, days, start)

    r0 = days[0]["results"]
    count = {s: sum(1 for r in r0 if r["status"] == s) for s in ("open", "closed", "unknown", "pending")}
    print(f"{start}: 開館 {count['open']} / 休館 {count['closed']} / 不明 {count['unknown']} / 準備中 {count['pending']}"
          f"（詳細あり {sum(1 for m in active if m['id'] in details)}/{len(active)} 館、閉館 {len(gone)} 館）")
    print(f"-> {SITE / 'index.html'} ほか {n_pages} ページ + sitemap.xml")

    if args.log:
        now = now_jst()
        entry = {
            "date": start.isoformat(), "finished_at": now.isoformat(timespec="seconds"),
            "checked_today": sum(1 for d in details.values() if d["checked_at"][:10] == today.isoformat()),
            "failed": [x for x in args.failed.split(",") if x], **count,
        }
        if args.started:
            entry["minutes"] = round((now - datetime.fromisoformat(args.started)).total_seconds() / 60, 1)
        if args.weekly_before is not None and args.weekly_after is not None:
            # 巡回 1 回がサブスクの週の枠を何 % 使ったか（全国対応の見積もりに使う）
            entry["weekly_usage"] = {"before": args.weekly_before, "after": args.weekly_after,
                                     "delta": args.weekly_after - args.weekly_before}
        with (DATA / "run_log.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
