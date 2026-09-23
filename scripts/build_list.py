"""Wikipedia「美術館の一覧」から対象都県の美術館を抜き出し、data/museums.json を作る。

    uv run scripts/build_list.py                       # 東京都・神奈川県
    uv run scripts/build_list.py --prefectures 東京都,千葉県
"""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass, asdict

from common import MUSEUMS_JSON, http, now_jst, read_json, write_json

LIST_TITLE = "美術館の一覧"
WP_API = "https://ja.wikipedia.org/w/api.php"
WD_API = "https://www.wikidata.org/w/api.php"
JAPANESE = "Q5287"

# 一覧の「日本」配下の小見出し → 区分
SECTIONS = {"国立": "国立", "国立以外の公立": "公立", "私立": "私立"}

LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


@dataclass
class Entry:
    name: str
    wiki_title: str  # 記事名（#節 付きのこともある）
    category: str
    prefecture: str


def fetch_wikitext(s) -> str:
    r = s.get(WP_API, params={"action": "parse", "page": LIST_TITLE, "prop": "wikitext",
                              "format": "json", "formatversion": 2}, timeout=30)
    r.raise_for_status()
    return r.json()["parse"]["wikitext"]


def parse_item(line: str) -> tuple[str, str] | None:
    """`* [[A|表示]]...` の先頭に連続するリンク群から (表示名, 記事名) を得る。

    `[[長泉院 (目黒区)|長泉院]][[長泉院附属現代彫刻美術館|附属現代彫刻美術館]]` のように
    リンクが連結されている場合、表示名は連結し、記事名は最後のリンクを採る。
    """
    rest = line.lstrip("*").strip()
    names, target = [], None
    while (m := LINK_RE.match(rest)):
        target = m.group(1).strip()
        names.append((m.group(2) or m.group(1)).strip())
        rest = rest[m.end():]
    if not target:
        return None
    return "".join(names), target


def split_sections(wikitext: str) -> dict[str, list[str]]:
    """日本の 国立/公立/私立 小見出しごとの行を返す。"""
    japan = wikitext.split("=== 日本 ===", 1)[1]
    japan = re.split(r"\n===[^=]", japan, maxsplit=1)[0]  # 次の国（=== 中国 ===）まで
    out, current = {}, None
    for line in japan.splitlines():
        if (m := re.match(r"^====\s*(.+?)\s*====\s*$", line)):
            current = SECTIONS.get(m.group(1))
            if current:
                out[current] = []
        elif current:
            out[current].append(line)
    return out


def extract(wikitext: str, prefectures: list[str]) -> list[Entry]:
    entries: list[Entry] = []
    for category, lines in split_sections(wikitext).items():
        pref = None
        for line in lines:
            if (m := re.match(r"^\|\s*(\S+?)\s*\|\s*$", line)):  # {{dl2 の `| 東京都 |`
                pref = m.group(1)
                continue
            if not line.startswith("*") or not (item := parse_item(line)):
                continue
            name, title = item
            if category == "国立":  # 国立は `* [[X]]（東京都）` 形式
                m = re.search(r"（(.+?)）\s*$", line)
                p = m.group(1) if m else None
            else:
                p = pref
            if p in prefectures:
                entries.append(Entry(name, title, category, p))
    return entries


def chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def resolve_qids(s, titles: list[str]) -> dict[str, str]:
    """記事名 → Wikidata QID（リダイレクト解決込み）。"""
    base = {t: t.split("#")[0] for t in titles}
    out: dict[str, str] = {}
    for batch in chunks(sorted(set(base.values())), 50):
        r = s.get(WP_API, params={"action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
                                  "titles": "|".join(batch), "redirects": 1, "format": "json",
                                  "formatversion": 2}, timeout=30)
        r.raise_for_status()
        q = r.json()["query"]
        alias = {}
        for key in ("normalized", "redirects"):
            for x in q.get(key, []):
                alias[x["from"]] = x["to"]
        by_title = {p["title"]: p.get("pageprops", {}).get("wikibase_item") for p in q["pages"]}
        for t in batch:
            final = t
            while final in alias:
                final = alias[final]
            if by_title.get(final):
                out[t] = by_title[final]
    return {t: out[b] for t, b in base.items() if b in out}


def fetch_entities(s, qids: list[str], props: str = "claims") -> dict:
    ents = {}
    for batch in chunks(sorted(set(qids)), 50):
        r = s.get(WD_API, params={"action": "wbgetentities", "ids": "|".join(batch), "props": props,
                                  "languages": "ja", "format": "json"}, timeout=30)
        r.raise_for_status()
        ents.update(r.json()["entities"])
    return ents


def claims(ent: dict, pid: str) -> list[dict]:
    cs = [c for c in ent.get("claims", {}).get(pid, []) if c.get("rank") != "deprecated"]
    return sorted(cs, key=lambda c: c.get("rank") != "preferred")


def value(c: dict):
    return c.get("mainsnak", {}).get("datavalue", {}).get("value")


def official_url(ent: dict) -> str | None:
    cs = claims(ent, "P856")
    ja = [c for c in cs if any(value(q) and value(q).get("id") == JAPANESE
                               for q in c.get("qualifiers", {}).get("P407", []))]
    for c in ja + cs:
        if (v := value(c)):
            return v
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prefectures", default="東京都,神奈川県")
    args = ap.parse_args()
    prefectures = [p.strip() for p in args.prefectures.split(",") if p.strip()]

    s = http()
    entries = extract(fetch_wikitext(s), prefectures)
    qid_of = resolve_qids(s, [e.wiki_title for e in entries])
    ents = fetch_entities(s, list(qid_of.values()))

    places = {value(c)["id"] for q in qid_of.values() for c in claims(ents.get(q, {}), "P131")[:1] if value(c)}
    place_label = {q: e.get("labels", {}).get("ja", {}).get("value")
                   for q, e in fetch_entities(s, list(places), "labels").items()} if places else {}

    previous = {m["id"]: m for m in read_json(MUSEUMS_JSON)["museums"]} if MUSEUMS_JSON.exists() else {}

    museums, seen = [], set()
    for e in entries:
        qid = qid_of.get(e.wiki_title)
        # 節リンク（中村屋#美術館 など）は記事の QID が館そのものを指さないので専用 ID にする
        if qid and "#" not in e.wiki_title:
            mid = qid
        else:
            mid = "wp-" + hashlib.sha1(e.name.encode()).hexdigest()[:8]
        if mid in seen:
            continue
        seen.add(mid)
        ent = ents.get(qid, {}) if qid and "#" not in e.wiki_title else {}
        coord = next((value(c) for c in claims(ent, "P625") if value(c)), None)
        p131 = next((value(c)["id"] for c in claims(ent, "P131") if value(c)), None)
        closed_on = next((value(c)["time"][1:11] for c in claims(ent, "P576") + claims(ent, "P3999") if value(c)), None)
        museums.append({
            "id": mid,
            "name": e.name,
            "wiki_title": e.wiki_title,
            "wikidata": qid if mid == qid else None,
            "category": e.category,
            "prefecture": e.prefecture,
            "municipality": place_label.get(p131),
            "official_url": official_url(ent),
            "lat": coord["latitude"] if coord else None,
            "lng": coord["longitude"] if coord else None,
            "status": "closed" if closed_on else "active",
            "closed_on": closed_on,
            "first_seen": previous.get(mid, {}).get("first_seen", now_jst().date().isoformat()),
        })

    write_json(MUSEUMS_JSON, {
        "source": f"https://ja.wikipedia.org/wiki/{LIST_TITLE}",
        "prefectures": prefectures,
        "generated_at": now_jst().isoformat(timespec="seconds"),
        "museums": museums,
    })

    by = {}
    for m in museums:
        by.setdefault((m["prefecture"], m["category"]), 0)
        by[(m["prefecture"], m["category"])] += 1
    print(f"{len(museums)} 館を書き出しました -> {MUSEUMS_JSON}")
    for (p, c), n in sorted(by.items()):
        print(f"  {p} {c}: {n}")
    print(f"  公式URLあり: {sum(1 for m in museums if m['official_url'])}")
    print(f"  Wikidata上で閉館: {[m['name'] for m in museums if m['status'] == 'closed']}")
    missing = [m["name"] for m in museums if not m["official_url"]]
    if missing:
        print(f"  公式URLなし: {missing}")


if __name__ == "__main__":
    main()
