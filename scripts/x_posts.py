"""X（@museum__watch）に投稿する文を巡回データから作る。投稿そのものはしない。

    uv run scripts/x_posts.py plan                 # 予約済みの続きの日（初回は明日）から 7 日分（12 時・19 時の 14 件）を data/x_queue.json に書き、一覧を出す
    uv run scripts/x_posts.py plan --start 2026-10-02 --days 7
    uv run scripts/x_posts.py done 1 2 5           # 一覧の番号の投稿を「予約済み」として data/x_posted.jsonl に記録する

投稿の種類（上から優先。同じ話題は二度と使わない。同じ日に同じ館は 1 回まで。同じ種類は続けない）:
    free      無料開放日（12 時はその日、19 時は翌日の分）
    ending    会期終了まで 3 日以内の展覧会
    new       開幕して 7 日以内の展覧会（企画展だけ。new と upcoming は同じ展覧会で 1 回）
    upcoming  7 日以内に始まる展覧会
    ending    会期終了まで 7 日以内の展覧会（19 時）
    museum    館の見どころ（AI の要約）。同じ館は 90 日あける
    promo     サイトの宣伝（いちばん長く使っていないもの）。7 日に 1 回は入れる

リンクはすべて公開ページの個別ページで、utm_source=x&utm_medium=social&utm_campaign=<種類> を付ける。
文字数は X の数え方（日本語 2、URL 23）で 280 以内に収める。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta

from common import DATA, MUSEUMS_JSON, SITE_URL, now_jst, read_json
from pages import FREE_SCOPE, exhibition_id, md
from render import judge, load_details

QUEUE = DATA / "x_queue.json"
POSTED = DATA / "x_posted.jsonl"
SLOTS = {"noon": "12:00", "evening": "19:00"}
WEEK = "月火水木金土日"
LIMIT = 280
MUSEUM_GAP_DAYS = 90
URGENT: dict[date, set[str]] = {}  # 会期末が今日・明日の展覧会（種類が続いても先に出す）

PROMOS = [
    ("", "今日開いている美術館、何時まで開いているか、入館料、開催中の展覧会。\n全国の美術館を毎週調べて、1 ページにまとめています。",
     "#美術館 #展覧会"),
    ("f/ending.html", "会期終了まで 2 週間以内の展覧会をまとめました。\n見逃す前にチェックを。", "#展覧会 #美術館巡り"),
    ("f/free.html", "大人一般が無料になる日を、6 週間先までカレンダーにしています。\n県民の日・都民の日・国際博物館の日なども。",
     "#無料開放 #美術館"),
    ("f/late.html", "19 時以降も開いている美術館の一覧です。\n仕事帰りの美術館に。", "#美術館 #夜間開館"),
    ("", "「行きたい」「行った」を館ごとに記録して、スマホと同期できます。\nホーム画面に追加すればアプリのように使えます。",
     "#美術館 #アート好きな人と繋がりたい"),
]


def weight(text: str) -> int:
    """X の文字数（twitter-text の重み付け）。URL は 23 として別に数える。"""
    n = 0
    for ch in text:
        o = ord(ch)
        light = o <= 0x10FF or 0x2000 <= o <= 0x200D or 0x2010 <= o <= 0x201F or 0x2032 <= o <= 0x2037
        n += 1 if light else 2
    return n


def length(body: str, url: str) -> int:
    return weight(body) + 1 + 23  # 改行 + URL


def link(path: str, kind: str) -> str:
    return f"{SITE_URL}{path}?utm_source=x&utm_medium=social&utm_campaign={kind}"


def fit(template: str, url: str, **fields: str) -> str:
    """長すぎるときは最後の差し込み（説明文・展覧会名）から削って 280 に収める。"""
    keys = list(fields)
    while True:
        body = template.format(**fields)
        if length(body, url) <= LIMIT:
            return f"{body}\n{url}".replace("\n\n\n", "\n\n")
        k = next((k for k in reversed(keys) if len(fields[k]) > 8), None)
        if k is None:
            raise ValueError(f"収まらない: {body}")
        fields[k] = fields[k][: max(8, len(fields[k]) - 10)].rstrip("、。 ") + "…"


def day_label(d: date) -> str:
    return f"{d.month}/{d.day}（{WEEK[d.weekday()]}）"


def load_posted() -> list[dict]:
    if not POSTED.exists():
        return []
    return [json.loads(l) for l in POSTED.read_text(encoding="utf-8").splitlines() if l.strip()]


def candidates(d: date, slot: str, museums: list[dict], details: dict, today: date) -> list[dict]:
    """その日・その枠に出せる投稿を優先順に並べる。key は重複を避けるための話題の名前。"""
    target = d if slot == "noon" else d + timedelta(days=1)
    when = "今日" if slot == "noon" else "明日"
    out: list[tuple[int, dict]] = []

    for m in museums:
        det = details[m["id"]]
        r = judge(m, det, target, today)
        f = r.get("free")
        if f and f["scope"] in ("all", "collection") and r["status"] == "open":
            what = FREE_SCOPE[f["scope"]]
            hours = f"{r['open']}–{r['close']}" if r["open"] and r["close"] else ""
            text = fit("【{when}は無料】{name}（{pref}）\n{what}{reason}\n{day} {hours}\n\n#美術館 #無料開放",
                       link(f"m/{m['id']}.html", "free"), when=when, name=m["name"], pref=m["prefecture"], what=what,
                       day=day_label(target), hours=hours, reason=f"：{f['reason']}" if f.get("reason") else "")
            out.append((0, {"key": f"free:{m['id']}:{target}", "museum": m["id"], "kind": "free", "text": text}))

        for e in det["exhibitions"]:
            if e["start"] > (d + timedelta(days=7)).isoformat() or e["end"] < d.isoformat():
                continue
            if e.get("kind") != "special":  # 企画展だけ（常設展・公募展・区民展などは宣伝しない）
                continue
            eid = exhibition_id(m["id"], e)
            url_path = f"e/{eid}.html"
            left = (date.fromisoformat(e["end"]) - d).days
            started = (d - date.fromisoformat(e["start"])).days
            base = {"museum": m["id"]}
            if e["start"] <= d.isoformat() and left <= 7:
                if slot == "evening" and left == 0:  # 19 時に「本日最終日」は間に合わない
                    continue
                pri = 1 if left <= 3 else 4
                head = "本日最終日" if left == 0 else f"会期終了まであと{left}日"
                if left <= 1:
                    URGENT.setdefault(d, set()).add(f"ending:{eid}")
                out.append((pri, base | {"key": f"ending:{eid}", "kind": "ending", "text": fit(
                    "【{head}】\n「{title}」\n{name}（{pref}）\n{end}まで\n\n#展覧会 #美術館",
                    link(url_path, "ending"), head=head, name=m["name"], pref=m["prefecture"],
                    end=day_label(date.fromisoformat(e["end"])), title=e["title"])}))
            elif 0 <= started <= 7:
                out.append((2, base | {"key": f"ex:{eid}", "kind": "new", "text": fit(
                    "【開催中】\n「{title}」\n{name}（{pref}）\n{end}まで\n{rec}\n\n#展覧会 #美術館",
                    link(url_path, "new"), name=m["name"], pref=m["prefecture"],
                    end=day_label(date.fromisoformat(e["end"])), title=e["title"], rec=e.get("recommend") or "")}))
            elif started < 0:
                out.append((3, base | {"key": f"ex:{eid}", "kind": "upcoming", "text": fit(
                    "【まもなく開幕】\n「{title}」\n{name}（{pref}）\n{start}〜{end}\n{rec}\n\n#展覧会 #美術館",
                    link(url_path, "upcoming"), name=m["name"], pref=m["prefecture"],
                    start=md(e["start"]), end=md(e["end"]), title=e["title"], rec=e.get("recommend") or "")}))

        if det.get("highlights") and judge(m, det, target, today)["status"] == "open":
            out.append((5, {"key": f"museum:{m['id']}", "museum": m["id"], "kind": "museum", "text": fit(
                "【美術館紹介】{name}（{pref}）\n{text}\n\n#美術館",
                link(f"m/{m['id']}.html", "museum"), name=m["name"], pref=m["prefecture"], text=det["highlights"])}))

    for i, (path, body, tags) in enumerate(PROMOS):
        out.append((6, {"key": f"promo:{i}", "museum": None, "kind": "promo",
                        "text": fit("{body}\n\n{tags}", link(path, "promo"), body=body, tags=tags)}))
    if slot == "evening":  # 夜は「明日」の話題と、会期末が近いものを先に
        out = [(0 if p == 0 else 1 if p in (1, 4) else p, c) for p, c in out]
    return [c for _, c in sorted(out, key=lambda x: x[0])]


def plan(start: date, days: int) -> list[dict]:
    today = now_jst().date()
    details = load_details()
    museums = [m for m in read_json(MUSEUMS_JSON)["museums"] if m["status"] != "closed" and m["id"] in details
               and details[m["id"]]["operating_status"] == "operating"]
    posted = load_posted()
    used = {p["key"]: date.fromisoformat(p["at"][:10]) for p in posted}
    queue = []
    last_kind = (posted[-1]["kind"] if posted else None)
    # 初回は数日たってから宣伝を入れる（最初の週は話題の投稿を先に）
    last_promo = max((date.fromisoformat(p["at"][:10]) for p in posted if p["kind"] == "promo"), default=start - timedelta(days=3))
    for i in range(days):
        d = start + timedelta(days=i)
        today_museums: set[str] = set()
        for slot, hm in SLOTS.items():
            def ok(c: dict) -> bool:
                last = used.get(c["key"])
                if c["kind"] == "museum":
                    return last is None or (d - last).days >= MUSEUM_GAP_DAYS
                if c["kind"] == "promo":
                    return True
                return last is None
            cs = [c for c in candidates(d, slot, museums, details, today) if ok(c) and c["museum"] not in today_museums]
            # 同じ種類が続かないようにする（無料開放日と、会期末が 1 日以内のものは続いてもよい）
            urgent = [c for c in cs if c["kind"] == "free" or c["key"] in URGENT.get(d, ())]
            fresh = [c for c in cs if c["kind"] != last_kind]
            # 宣伝は 7 日に 1 回は入れる
            promo_due = [c for c in cs if c["kind"] == "promo"] if (d - last_promo).days >= 7 else []
            cs = urgent + promo_due + fresh + cs
            promos = [c for c in cs if c["kind"] == "promo"]
            if promos:  # 宣伝はいちばん長く使っていないものだけ残す
                oldest = min(promos, key=lambda c: used.get(c["key"], date.min))
                cs = [c for c in cs if c["kind"] != "promo" or c is oldest]
            c = cs[0]
            last_kind = c["kind"]
            if c["kind"] == "promo":
                last_promo = d
            used[c["key"]] = d
            if c["museum"]:
                today_museums.add(c["museum"])
            queue.append({"no": len(queue) + 1, "at": f"{d}T{hm}:00+09:00", "slot": slot} | c)
    return queue


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--start", type=date.fromisoformat, default=None, help="初期値は予約済みの最後の日の翌日（初回は明日）")
    p.add_argument("--days", type=int, default=7)
    dn = sub.add_parser("done")
    dn.add_argument("numbers", type=int, nargs="+")
    args = ap.parse_args()

    if args.cmd == "plan":
        tomorrow = now_jst().date() + timedelta(days=1)
        last = max((date.fromisoformat(p["at"][:10]) for p in load_posted()), default=None)
        start = args.start or max(tomorrow, last + timedelta(days=1) if last else tomorrow)
        queue = plan(start, args.days)
        QUEUE.write_text(json.dumps(queue, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        for q in queue:
            at = datetime.fromisoformat(q["at"])
            print(f"── {q['no']}. {day_label(at.date())} {at:%H:%M}  [{q['kind']}]  {length(q['text'].rsplit(chr(10), 1)[0], '')}/280")
            print(q["text"])
        return

    queue = {q["no"]: q for q in json.loads(QUEUE.read_text(encoding="utf-8"))}
    missing = [n for n in args.numbers if n not in queue]
    if missing:
        sys.exit(f"一覧に無い番号: {missing}")
    with POSTED.open("a", encoding="utf-8") as f:
        for n in args.numbers:
            q = queue[n]
            f.write(json.dumps({"at": q["at"], "key": q["key"], "kind": q["kind"], "text": q["text"],
                                "scheduled_at": now_jst().isoformat(timespec="seconds")}, ensure_ascii=False) + "\n")
    print(f"{len(args.numbers)} 件を記録しました")


if __name__ == "__main__":
    main()
