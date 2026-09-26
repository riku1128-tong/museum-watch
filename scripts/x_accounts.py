"""各館の X（旧 Twitter）公式アカウントを洗い出して data/x_accounts.json に書く。@museum__watch からフォローする相手の一覧用。

    uv run scripts/x_accounts.py

探す場所（上から優先）:
    wikidata   Wikidata の P2002（X のユーザー名）。終了日（P582）の付いたものは除く
    site       公式サイトのトップページにある x.com / twitter.com へのリンク（共有ボタンなどは除き、いちばん多く出てくるもの）。
               自治体の広報など館ではないアカウントは NOT_MUSEUM で除く。見た目で確かめたものではないので、一覧では「要確認」

見つからなかった館は handle: null。アカウントが今も使われているか（凍結・改名）までは確かめない。
"""

from __future__ import annotations

import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import requests

from common import DATA, DETAILS, MUSEUMS_JSON, PREFS, http, read_json

WD_API = "https://www.wikidata.org/w/api.php"
OUT = DATA / "x_accounts.json"
LINK = re.compile(r"https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/(?:#!/)?@?([A-Za-z0-9_]{1,15})(?=[/?\"'#\s<]|$)")
NOT_ACCOUNTS = {"share", "intent", "home", "hashtag", "search", "i", "login", "signup", "privacy", "tos", "settings",
                "explore", "x", "twitter", "widgets", "messages", "notifications", "compose", "en", "ja", "about",
                "download", "jobs", "rules"}
# 公式サイトから拾ったが館のアカウントではないもの（自治体の広報・放送局・展覧会だけの期間限定アカウント・無関係の埋め込み）
NOT_MUSEUM = {"otarucity", "akitacity", "komorocity", "okazaki_koho", "tanabecity", "hashimacity", "minamiawajicity",
              "kouhou_toyooka", "rnc_tvradio", "oknwsen14movie", "muttoni6_y2026", "ruheteahouse", "sohgo_sawada",
              "koyafron", "pekita946", "art_ex_japan"}


def from_wikidata(s: requests.Session, qids: list[str]) -> dict[str, str]:
    out = {}
    for i in range(0, len(qids), 50):
        r = s.get(WD_API, params={"action": "wbgetentities", "ids": "|".join(qids[i:i + 50]), "props": "claims",
                                  "format": "json"}, timeout=30)
        r.raise_for_status()
        for qid, ent in r.json()["entities"].items():
            cs = [c for c in ent.get("claims", {}).get("P2002", [])
                  if c.get("rank") != "deprecated" and not c.get("qualifiers", {}).get("P582")]
            cs.sort(key=lambda c: c.get("rank") != "preferred")
            v = next((c["mainsnak"].get("datavalue", {}).get("value") for c in cs), None)
            if v:
                out[qid] = v
    return out


def from_site(url: str) -> str | None:
    s = http()
    s.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
    try:
        r = s.get(url, timeout=15)
        r.encoding = r.apparent_encoding if r.encoding in (None, "ISO-8859-1") else r.encoding
        text = r.text
    except requests.RequestException:
        return None
    found = Counter(h for h in LINK.findall(text) if h.lower() not in NOT_ACCOUNTS | NOT_MUSEUM)
    return found.most_common(1)[0][0] if found else None


def main() -> None:
    ms = [m for m in read_json(MUSEUMS_JSON)["museums"] if m["status"] != "closed"]
    ms.sort(key=lambda m: (PREFS.index(m["prefecture"]), m["name"]))
    s = http()
    wd = from_wikidata(s, [m["wikidata"] for m in ms if m.get("wikidata")])

    def site_url(m: dict) -> str | None:
        path = DETAILS / f"{m['id']}.json"
        return (read_json(path).get("official_url") if path.exists() else None) or m.get("official_url")

    todo = [m for m in ms if m.get("wikidata") not in wd and site_url(m)]
    with ThreadPoolExecutor(16) as ex:
        site = dict(zip([m["id"] for m in todo], ex.map(lambda m: from_site(site_url(m)), todo)))

    rows = []
    for m in ms:
        handle, source = (wd[m["wikidata"]], "wikidata") if m.get("wikidata") in wd else (site.get(m["id"]), "site")
        rows.append({"id": m["id"], "name": m["name"], "prefecture": m["prefecture"],
                     "handle": handle, "source": source if handle else None,
                     "url": f"https://x.com/{handle}" if handle else None})
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(1 for r in rows if r["handle"])
    by = Counter(r["source"] for r in rows if r["handle"])
    shared = Counter(r["handle"].lower() for r in rows if r["handle"])
    print(f"{n}/{len(rows)} 館で見つかった（Wikidata {by['wikidata']}・公式サイト {by['site']}）。"
          f"重複を除いたアカウント数 {len(shared)}")


if __name__ == "__main__":
    main()
