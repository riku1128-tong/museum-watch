"""アフィリエイトの枠。data/affiliates.json で有効（enabled: true）にした提携先だけを表示する。

提携先の url には次の差し込みが使える（URL エンコードして埋め込む）:
    {name}          館の名前
    {prefecture}    都道府県
    {municipality}  地名。観光地（areas.AREAS）の中なら地域名（箱根など）、それ以外は市区町村、無ければ都道府県
    {title}         展覧会の名前（展覧会の枠のときだけ。無ければ館の名前）
    {placement}     置き場所（route / museum / exhibition / area）。ASP のサブ ID に入れて、置き場所ごとの成約を見る
    {museum_id}     館の ID（Wikidata の Q 番号）。同じくサブ ID 用

置き場所（placements）:
    route       トップページの「行き方」シート
    museum      館のページ
    exhibition  展覧会のページ
    area        観光地の特集ページ（f/area-*.html）。館ごとではなく地域に 1 つ

リンクには「PR」を表示し、rel="sponsored" を付ける。クリックは GA4 の affiliate_click で計測する。
"""

from __future__ import annotations

import json
from html import escape
from urllib.parse import quote

from areas import place_name
from common import DATA

CONFIG = DATA / "affiliates.json"


def load() -> list[dict]:
    if not CONFIG.exists():
        return []
    return [p for p in json.loads(CONFIG.read_text(encoding="utf-8")).get("partners", []) if p.get("enabled")]


def fill(template: str, m: dict, e: dict | None = None, placement: str = "") -> str:
    values = {"name": m["name"], "prefecture": m["prefecture"],
              "municipality": place_name(m),
              "title": (e or {}).get("title") or m["name"],
              "placement": placement, "museum_id": m.get("id", "")}
    out = template
    for k, v in values.items():
        out = out.replace("{" + k + "}", quote(v))
    return out


def links_html(placement: str, m: dict, e: dict | None = None) -> str:
    """静的ページ用の枠。有効な提携先が無ければ空文字（何も表示しない）。"""
    ps = [p for p in load() if placement in p.get("placements", [])]
    if not ps:
        return ""
    links = "".join(
        f'<a class="aff btn ghost" href="{escape(fill(p["url"], m, e, placement))}" target="_blank" rel="sponsored noopener" '
        f'data-partner="{escape(p["id"])}" data-placement="{placement}" data-museum-id="{escape(m["id"])}" '
        f'data-museum-name="{escape(m["name"])}">{escape(p["label"])}</a>' for p in ps)
    return f'<aside class="aff-box" aria-label="広告"><span class="pr">PR</span><div class="row">{links}</div></aside>'


def for_js() -> list[dict]:
    """トップページの「行き方」シートで使う提携先（ページ側で差し込みを埋める）。"""
    return [{"id": p["id"], "label": p["label"], "url": p["url"]} for p in load() if "route" in p.get("placements", [])]
