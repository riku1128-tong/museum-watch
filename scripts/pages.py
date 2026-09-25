"""検索から人が来るための静的ページ（館・展覧会・都道府県）と sitemap.xml を docs/ に書き出す。render.py から呼ばれる。

    docs/m/<館id>.html        館ごとのページ（開館時間・休館日・料金・アクセス・14 日分の開館カレンダー・展覧会）
    docs/e/<展覧会id>.html    展覧会ごとのページ（会期・料金・開催館）
    docs/p/<都道府県コード>.html 都道府県ごとの館の一覧
    docs/sitemap.xml          上記と トップページの一覧（noindex のページは含めない）

まだ巡回していない館のページは中身が薄いので noindex にし、sitemap にも入れない。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import date
from html import escape

from common import GA_ID, PREFS, REGIONS, SITE, SITE_URL
from affiliate import links_html
from render import exhibition_price, museum_price

WD_JA = {"mon": "月", "tue": "火", "wed": "水", "thu": "木", "fri": "金", "sat": "土", "sun": "日", "holiday": "祝"}
WD_EN = {"mon": "Monday", "tue": "Tuesday", "wed": "Wednesday", "thu": "Thursday", "fri": "Friday",
         "sat": "Saturday", "sun": "Sunday"}
STATUS_JA = {"open": "開館", "closed": "休館", "unknown": "不明", "pending": "準備中"}
FREE_SCOPE = {"all": "無料開放日", "collection": "常設展 無料開放日", "partial": "一部無料開放日"}


def pref_code(pref: str) -> str:
    return f"{PREFS.index(pref) + 1:02d}"


def exhibition_id(museum_id: str, e: dict) -> str:
    return hashlib.sha1(f"{museum_id}|{e['title']}|{e['start']}".encode()).hexdigest()[:10]


def md(iso: str, ref: date | None = None) -> str:
    y, m, d = iso.split("-")
    s = f"{int(m)}/{int(d)}"
    return s if ref is None or int(y) == ref.year else f"{y}/{s}"


def yen(n: int | None) -> str:
    return "" if n is None else ("無料" if n == 0 else f"¥{n:,}")


ORDER = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def days_text(days: list[str]) -> str:
    """曜日の並びを読みやすくする。例: 全曜日 → 毎日、火〜日 → 火〜日曜、月・水・金 → 月・水・金曜、祝日は「祝日」と書く。"""
    idx = sorted(ORDER.index(d) for d in set(days) if d in ORDER)
    runs, run = [], []
    for i in idx:
        if run and i != run[-1] + 1:
            runs.append(run); run = []
        run.append(i)
    if run:
        runs.append(run)
    if len(idx) == 7:
        text = "毎日"
    elif idx:
        text = "・".join(WD_JA[ORDER[r[0]]] + ("〜" + WD_JA[ORDER[r[-1]]] if len(r) >= 3 else
                                               "・" + WD_JA[ORDER[r[-1]]] if len(r) == 2 else "") for r in runs) + "曜"
    else:
        text = ""
    if "holiday" in days:
        text = f"{text}・祝日" if text and text != "毎日" else (text or "祝日")
    return text


def hours_rows(hours: list[dict], today: date, closed: list[str] = ()) -> list[str]:
    """通常の時間定義を「曜日 時間」の行にする。毎週の定休日は曜日から除く（休館日の欄と矛盾させない）。
    期間限定のものは期間を添え、終わったものは出さない。"""
    rows = []
    for h in sorted(hours, key=lambda h: (h.get("from") is not None, -len(h["days"]))):
        if h.get("to") and h["to"] < today.isoformat():
            continue
        period = (f"（{md(h['from'], today) if h.get('from') else ''}〜{md(h['to'], today) if h.get('to') else ''}）"
                  if h.get("from") or h.get("to") else "")
        last = f"・最終入館 {h['last_entry']}" if h.get("last_entry") else ""
        days = [d for d in h["days"] if d not in closed or d == "holiday"]
        if not days:
            continue
        rows.append(f"{days_text(days)} {h['open']}–{h['close']}{last}{period}")
    return rows


def closed_text(det: dict) -> str:
    parts = []
    weekly = [d for d in det["closed_weekdays"] if d != "holiday"]
    if weekly:
        parts.append("毎週" + days_text(weekly))
    if "holiday" in det["closed_weekdays"]:
        parts.append("祝日")
    for r in det.get("closed_nth_weekdays", []):
        parts.append("第" + "・第".join(map(str, r["nth"])) + WD_JA[r["weekday"]] + "曜")
    if not parts:
        return "定休日なし" if det["holiday_rule"] != "unknown" else "公式サイトでご確認ください"
    rule = {"open_next_weekday_closed": "（祝日の場合は開館し、翌平日が休館）", "open": "（祝日の場合は開館）",
            "closed": "", "unknown": ""}[det["holiday_rule"]]
    return "、".join(parts) + rule


def access_text(a: dict) -> str:
    """最寄駅 1 件を「JR山手線「上野」駅 公園口 から徒歩1分（バスは…）」の形にする。"""
    text = f"{a.get('lines') or ''}「{a['station']}」駅"
    if a.get("exit"):
        text += f" {a['exit']}"
    if a.get("walk_min") is not None:
        text += f" から徒歩{a['walk_min']}分"
    if a.get("note"):
        text += f"（{a['note']}）"
    return text


def utm(url: str, campaign: str, content: str = "") -> str:
    """外部サイトへのリンクに UTM を付ける（campaign = リンクの置き場所、content = 館 ID）。サイト内のリンクには使わない。"""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    try:
        u = urlsplit(url)
        q = dict(parse_qsl(u.query, keep_blank_values=True))
        q.update({"utm_source": "museum-watch", "utm_medium": "referral", "utm_campaign": campaign,
                  **({"utm_content": content} if content else {})})
        return urlunsplit(u._replace(query=urlencode(q)))
    except ValueError:
        return url


def ga_snippet() -> str:
    """GA4 の計測タグ。手元の確認用サーバー（localhost）では読み込まない。"""
    if not GA_ID:
        return ""
    return f"""<script>
  // Google アナリティクス（GA4）。localhost では計測しない（確認作業でアクセス数を水増ししないため）
  window.dataLayer = window.dataLayer || [];
  function gtag() {{ dataLayer.push(arguments); }}
  if (!/^(localhost|127\\.0\\.0\\.1)$/.test(location.hostname)) {{
    const s = document.createElement("script"); s.async = true;
    s.src = "https://www.googletagmanager.com/gtag/js?id={GA_ID}"; document.head.appendChild(s);
    gtag("js", new Date()); gtag("config", "{GA_ID}");
  }}
</script>"""


def page(*, title: str, desc: str, path: str, body: str, depth: int, jsonld: list[dict] | None = None,
         noindex: bool = False) -> str:
    up = "../" * depth
    ld = "".join(f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False)}</script>'
                 for j in (jsonld or []))
    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="manifest" href="{up}manifest.webmanifest">
<link rel="apple-touch-icon" href="{up}icons/apple-touch-icon.png">
<meta name="theme-color" content="#efece6" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#141312" media="(prefers-color-scheme: dark)">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="美術館ウォッチ">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>{escape(title)}</title>
<meta name="description" content="{escape(desc)}">
<link rel="canonical" href="{SITE_URL}{path}">
{'<meta name="robots" content="noindex">' if noindex else ''}
<meta property="og:type" content="website">
<meta property="og:title" content="{escape(title)}">
<meta property="og:description" content="{escape(desc)}">
<meta property="og:url" content="{SITE_URL}{path}">
<meta property="og:site_name" content="美術館ウォッチ">
<script>
  try {{ const t = localStorage.getItem("mw:theme"); if (t === "light" || t === "dark") document.documentElement.dataset.theme = t; }} catch {{}}
</script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600&family=Shippori+Mincho:wght@500;700&family=Zen+Kaku+Gothic+New:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{up}style.css">
{ga_snippet()}
<script>
  // ホーム画面に追加したときのオフライン表示のための Service Worker
  if ("serviceWorker" in navigator) addEventListener("load", () => navigator.serviceWorker.register("{up}sw.js").catch(() => {{}}));
</script>
<script>
  // アフィリエイトのリンクのクリックを GA4 に送る（提携先・置き場所・館）
  document.addEventListener("click", (e) => {{
    const a = e.target.closest("a.aff"); if (!a || !window.gtag) return;
    gtag("event", "affiliate_click", {{ partner: a.dataset.partner, placement: a.dataset.placement,
      museum_id: a.dataset.museumId, museum_name: a.dataset.museumName }});
  }});
</script>
{ld}
</head>
<body class="doc">
<header class="doc-head">
  <a class="overline" href="{up}index.html">Museum Watch</a>
  <a class="doc-brand" href="{up}index.html">美術館ウォッチ</a>
</header>
<div class="rule"><hr></div>
<main class="doc-main">
{body}
</main>
<footer>
  情報は各館の公式サイトから自動で集めたもので、変更が反映されていないことがあります。お出かけ前に公式サイトでご確認ください。
  館の一覧: <a href="https://ja.wikipedia.org/wiki/美術館の一覧" target="_blank" rel="noopener">Wikipedia</a>（CC BY-SA 4.0）・Wikidata ／
  <a href="{up}index.html">今日開いている美術館を探す</a> ／ <a href="{up}f/index.html">特集</a><br>
  <a href="{up}about.html">運営者情報・お問い合わせ</a> ／ <a href="{up}disclaimer.html">免責事項</a> ／ <a href="{up}privacy.html">プライバシーポリシー</a>
</footer>
</body>
</html>
"""


def museum_jsonld(m: dict, det: dict | None) -> dict:
    ld = {"@context": "https://schema.org", "@type": "Museum", "name": m["name"],
          "url": (det or {}).get("official_url") or m.get("official_url"),
          "address": {"@type": "PostalAddress", "addressRegion": m["prefecture"], "addressCountry": "JP",
                      **({"streetAddress": det["address"]} if det and det.get("address") else {})}}
    if m.get("lat") is not None:
        ld["geo"] = {"@type": "GeoCoordinates", "latitude": m["lat"], "longitude": m["lng"]}
    if det:
        ld["openingHoursSpecification"] = [
            {"@type": "OpeningHoursSpecification", "dayOfWeek": [WD_EN[d] for d in h["days"] if d in WD_EN],
             "opens": h["open"], "closes": h["close"],
             **({"validFrom": h["from"]} if h.get("from") else {}), **({"validThrough": h["to"]} if h.get("to") else {})}
            for h in det["regular_hours"]]
    return {k: v for k, v in ld.items() if v}


def exhibition_jsonld(m: dict, det: dict, e: dict) -> dict:
    price = exhibition_price(e)
    ld = {"@context": "https://schema.org", "@type": "ExhibitionEvent", "name": e["title"],
          "startDate": e["start"], "endDate": e["end"], "eventStatus": "https://schema.org/EventScheduled",
          "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
          "location": {"@type": "Museum", "name": m["name"],
                       "address": {"@type": "PostalAddress", "addressRegion": m["prefecture"], "addressCountry": "JP",
                                   **({"streetAddress": det["address"]} if det.get("address") else {})}}}
    if e.get("summary"):
        ld["description"] = e["summary"]
    if e.get("url"):
        ld["url"] = e["url"]
    if price is not None:
        ld["offers"] = {"@type": "Offer", "price": price, "priceCurrency": "JPY", **({"url": e["url"]} if e.get("url") else {})}
    return ld


def calendar_table(results: list[tuple[dict, dict]]) -> str:
    rows = []
    for day, r in results:
        d = date.fromisoformat(day["date"])
        label = f"{d.month}/{d.day}（{day['weekday']}{'・祝' if day['holiday'] else ''}）"
        hours = f"{r['open']}–{r['close']}" if r["status"] == "open" and r.get("open") else ""
        free = r.get("free")
        note = " ".join(x for x in [r.get("reason") or "", FREE_SCOPE[free["scope"]] if free else ""] if x)
        rows.append(f'<tr data-date="{day["date"]}" class="st-{r["status"]}{" free" if free and r["status"] == "open" else ""}"><th>{label}</th>'
                    f'<td>{STATUS_JA[r["status"]]}</td><td>{hours}</td><td>{escape(note)}</td></tr>')
    # ページは週 1 回しか作り直さないので、開いた日より前の行は隠し、その日の行に「今日」を付ける
    script = """<script>
  (() => {
    const t = new Date(Date.now() + 9 * 3600e3).toISOString().slice(0, 10);
    for (const tr of document.querySelectorAll("table.cal tr[data-date]")) {
      if (tr.dataset.date < t) tr.hidden = true;
      if (tr.dataset.date === t) { tr.classList.add("today"); tr.querySelector("th").insertAdjacentHTML("beforeend", " <b>今日</b>"); }
    }
  })();
</script>"""
    return (f'<table class="cal"><thead><tr><th>日付</th><th>状況</th><th>時間</th><th>メモ</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
            + script)


def exhibition_item(m: dict, e: dict, today: date, link: bool = True) -> str:
    price = exhibition_price(e)
    title = f'<a href="../e/{exhibition_id(m["id"], e)}.html">{escape(e["title"])}</a>' if link else escape(e["title"])
    meta = " ・ ".join(x for x in [f"{md(e['start'], today)} – {md(e['end'], today)}",
                                   f"一般 {yen(price)}" if price is not None else "",
                                   "企画展" if e.get("kind") == "special" else "常設展・コレクション展" if e.get("kind") == "collection" else ""] if x)
    return (f'<li class="{"special" if e.get("kind") == "special" else ""}"><div class="ex-title">{title}</div>'
            f'<div class="ex-meta">{meta}</div>{f"<div class=ex-sum>{escape(e["summary"])}</div>" if e.get("summary") else ""}'
            f'{f"<div class=ex-rec><b>おすすめ</b> {escape(e["recommend"])}</div>" if e.get("recommend") else ""}</li>')


def museum_page(m: dict, det: dict | None, cal: list[tuple[dict, dict]], today: date) -> str:
    place = f"{m['prefecture']}{(' ' + m['municipality']) if m.get('municipality') and m['municipality'] != m['prefecture'] else ''}"
    url = (det or {}).get("official_url") or m.get("official_url")
    crumbs = (f'<nav class="crumbs"><a href="../index.html">全国</a> › '
              f'<a href="../p/{pref_code(m["prefecture"])}.html">{escape(m["prefecture"])}</a> › {escape(m["name"])}</nav>')
    official = f'<a href="{escape(utm(url, "museum_page_official", m["id"]))}" target="_blank" rel="noopener">公式サイト</a>' if url else ""
    head = f'{crumbs}<h1>{escape(m["name"])}</h1><p class="lead">{escape(place)} ・ {escape(m["category"])}{" ・ " + official if official else ""}</p>'
    if not det:
        body = head + ('<section><p>開館時間と展覧会の情報は、毎週の巡回で順番に集めています。'
                       f'{"今は" + official + "でご確認ください。" if official else ""}</p></section>')
        return page(title=f"{m['name']}｜美術館ウォッチ", desc=f"{m['name']}（{place}）の情報を準備中です。",
                    path=f"m/{m['id']}.html", body=body, depth=1, jsonld=[museum_jsonld(m, None)], noindex=True)

    t = today.isoformat()
    current = [e for e in det["exhibitions"] if e["start"] <= t <= e["end"]]
    upcoming = sorted((e for e in det["exhibitions"] if e["start"] > t), key=lambda e: e["start"])
    price = museum_price(det)
    info = [("開館時間", "<br>".join(escape(x) for x in hours_rows(det["regular_hours"], today, det["closed_weekdays"])) or "公式サイトでご確認ください"),
            ("休館日", escape(closed_text(det))),
            ("料金（大人一般）", yen(price) if price is not None else "展覧会により異なります（下の展覧会の料金をご覧ください）")]
    if det.get("address"):
        info.append(("住所", escape(det["address"])))
    if det.get("access"):
        info.append(("最寄駅", "<br>".join(escape(access_text(a)) for a in det["access"])))
    closures = [c for c in det["special_closures"] if c["to"] >= t]
    if closures:
        info.append(("臨時休館", "<br>".join(escape(f"{md(c['from'], today)}〜{md(c['to'], today)} {c.get('reason') or ''}") for c in closures)))
    frees = [f for f in det.get("free_days", []) if f["to"] >= t]
    if frees:
        info.append(("無料開放日", "<br>".join(escape(
            f"{md(f['from'], today)}{'〜' + md(f['to'], today) if f['to'] != f['from'] else ''} {FREE_SCOPE[f['scope']]}"
            f"{'（' + '・'.join(f.get('targets', [])) + '）' if f.get('targets') else ''} {f.get('reason') or ''}") for f in frees)))
    if det.get("status_note"):
        info.insert(0, ("お知らせ", escape(det["status_note"])))
    dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in info)

    body = head
    if det.get("highlights"):
        body += (f'<section class="ai"><h2>この美術館の見どころ</h2><p>{escape(det["highlights"])}</p>'
                 f'<p class="ai-note">AI による要約（公式サイトの情報をもとに作成）</p></section>')
    body += f'<section><h2>基本情報</h2><dl class="info">{dl}</dl></section>' + links_html("museum", m)
    body += f'<section><h2>開館カレンダー（{md(cal[0][0]["date"])}〜{md(cal[-1][0]["date"])}）</h2>{calendar_table(cal)}</section>'
    if current:
        body += f'<section><h2>開催中の展覧会</h2><ul class="ex">{"".join(exhibition_item(m, e, today) for e in current)}</ul></section>'
    if upcoming:
        body += f'<section><h2>これからの展覧会</h2><ul class="ex">{"".join(exhibition_item(m, e, today) for e in upcoming)}</ul></section>'
    body += f'<p class="checked">公式サイトの確認: {det["checked_at"][:10]}</p>'

    titles = "・".join(e["title"] for e in current[:2])
    desc = (f"{m['name']}（{place}）の開館時間・休館日・料金（大人一般{' ' + yen(price) if price is not None else ''}）と、"
            f"開催中の展覧会{('「' + titles + '」') if titles else ''}。今日から2週間の開館カレンダー付き。毎週更新。")
    ld = [museum_jsonld(m, det)] + [exhibition_jsonld(m, det, e) for e in current + upcoming]
    return page(title=f"{m['name']}の開館時間・休館日・料金・展覧会｜美術館ウォッチ", desc=desc,
                path=f"m/{m['id']}.html", body=body, depth=1, jsonld=ld)


def exhibition_page(m: dict, det: dict, e: dict, today: date) -> str:
    price = exhibition_price(e)
    crumbs = (f'<nav class="crumbs"><a href="../index.html">全国</a> › '
              f'<a href="../p/{pref_code(m["prefecture"])}.html">{escape(m["prefecture"])}</a> › '
              f'<a href="../m/{m["id"]}.html">{escape(m["name"])}</a></nav>')
    info = [("会期", f"{e['start'].replace('-', '/')} 〜 {e['end'].replace('-', '/')}"),
            ("会場", f'<a href="../m/{m["id"]}.html">{escape(m["name"])}</a>（{escape(m["prefecture"])}）'),
            ("料金（一般）", yen(price) if price is not None else escape(e.get("admission") or "公式サイトでご確認ください"))]
    if e.get("hours"):
        info.append(("開館時間", "<br>".join(escape(x) for x in hours_rows(e["hours"], today, det["closed_weekdays"] + e.get("closed_weekdays", [])))))
    else:
        info.append(("開館時間", "<br>".join(escape(x) for x in hours_rows(det["regular_hours"], today, det["closed_weekdays"])) or "公式サイトでご確認ください"))
    info.append(("休館日", escape(closed_text(det))))
    if e.get("url"):
        info.append(("公式ページ", f'<a href="{escape(utm(e["url"], "exhibition_page_official", m["id"]))}" target="_blank" rel="noopener">展覧会の公式ページ</a>'))
    dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in info)
    body = (crumbs + f'<h1>{escape(e["title"])}</h1><p class="lead">{escape(m["name"])} ・ {md(e["start"], today)} – {md(e["end"], today)}</p>'
            + (f'<p>{escape(e["summary"])}</p>' if e.get("summary") else "")
            + (f'<section class="ai"><h2>この展覧会のおすすめポイント</h2><p>{escape(e["recommend"])}</p>'
               f'<p class="ai-note">AI による要約（公式の紹介文をもとに作成）</p></section>' if e.get("recommend") else "")
            + f'<section><h2>展覧会の情報</h2><dl class="info">{dl}</dl></section>' + links_html("exhibition", m, e)
            + f'<p><a href="../m/{m["id"]}.html">{escape(m["name"])}の開館カレンダー・ほかの展覧会を見る</a></p>')
    desc = (f"{e['title']}（{m['name']}）の会期{md(e['start'], today)}〜{md(e['end'], today)}、"
            f"料金{(' ' + yen(price)) if price is not None else ''}、開館時間と休館日。" + (e.get("recommend") or e.get("summary") or ""))
    return page(title=f"{e['title']}｜{m['name']}｜会期・料金・開館時間", desc=desc[:160],
                path=f"e/{exhibition_id(m['id'], e)}.html", body=body, depth=1, jsonld=[exhibition_jsonld(m, det, e)])


def prefecture_page(pref: str, museums: list[dict], details: dict, today_results: dict, today: date) -> str:
    items = []
    for m in sorted(museums, key=lambda m: (m["id"] not in details, m["name"])):
        r = today_results.get(m["id"], {"status": "pending"})
        det = details.get(m["id"])
        hours = f" {r['open']}–{r['close']}" if r["status"] == "open" and r.get("open") else ""
        titles = "・".join(e["title"] for e in r.get("exhibitions", [])[:2]) if det else ""
        items.append(f'<li><a href="../m/{m["id"]}.html">{escape(m["name"])}</a>'
                     f'<span class="pl-meta">{" ・ ".join(escape(x) for x in [m.get("municipality") or "", m["category"], f"{today.month}/{today.day}（{'月火水木金土日'[today.weekday()]}）時点: {STATUS_JA[r['status']]}{hours}"] if x)}</span>'
                     f'{f"<span class=pl-ex>{escape(titles)}</span>" if titles else ""}</li>')
    region = next(r for r, ps in REGIONS.items() if pref in ps)
    body = (f'<nav class="crumbs"><a href="../index.html">全国</a> › {escape(region)} › {escape(pref)}</nav>'
            f'<h1>{escape(pref)}の美術館</h1><p class="lead">{len(museums)} 館。開館時間・休館日・料金・開催中の展覧会を毎週更新しています。</p>'
            f'<p class="checked">開館状況は {today.month}/{today.day} 時点のものです（毎週更新）。各館のページで、その先 2 週間の開館カレンダーを見られます。</p><ul class="pref-list">{"".join(items)}</ul>')
    names = "・".join(m["name"] for m in museums[:4])
    return page(title=f"{pref}の美術館一覧（開館時間・休館日・展覧会）｜美術館ウォッチ",
                desc=f"{pref}の美術館{len(museums)}館（{names}ほか）の、今日の開館状況・開館時間・料金・開催中の展覧会。",
                path=f"p/{pref_code(pref)}.html", body=body, depth=1)


def privacy_page() -> str:
    """プライバシーポリシー（アクセス解析・端末間同期・位置検索・外部サービスへの送信）。"""
    body = """<h1>プライバシーポリシー</h1>
<p class="lead">美術館ウォッチ（以下「本サイト」）での情報の取り扱いについて説明します。</p>
<section><h2>アクセス解析（Google アナリティクス）</h2>
<p>本サイトは、利用状況を把握してサイトを改善するために、Google LLC の「Google アナリティクス」を使っています。
Google アナリティクスは Cookie などを使い、閲覧したページ、参照元、おおよその地域、端末やブラウザの種類などの情報を収集します。
個人を特定する情報は含まれません。</p>
<p>本サイトでは、ボタンの利用状況（「行きたい」「行った」「行き方」、並び順・絞り込みの変更、ログインの有無）も計測しています。
計測するのは館の識別子や選んだ項目の名前だけで、出発地・メールアドレス・訪問の記録そのものは送りません。</p>
<p>収集されたデータは Google のプライバシーポリシーに基づいて管理されます。
計測を望まない場合は、<a href="https://tools.google.com/dlpage/gaoptout?hl=ja" target="_blank" rel="noopener">Google アナリティクス オプトアウト アドオン</a>
を使うか、ブラウザの Cookie を無効にしてください。詳しくは
<a href="https://policies.google.com/technologies/partner-sites?hl=ja" target="_blank" rel="noopener">Google のサービスを使用するサイトやアプリから収集した情報の Google による使用</a>
をご覧ください。</p></section>
<section><h2>この端末に保存する情報</h2>
<p>「行きたい」「行った」の記録、出発地、よく見る地域、表示テーマなどは、お使いのブラウザ（localStorage）に保存します。
ブラウザのサイトデータを消すと削除されます。</p></section>
<section><h2>端末間の同期（ログインした場合のみ）</h2>
<p>設定画面でメールアドレスによるログインをすると、上記の記録を端末間で同期するため、Supabase（Supabase, Inc.）のサーバーに保存します。
保存するのは、ログイン用のメールアドレス、訪問の記録（館・日付）、行きたい館、出発地とその位置、よく見る地域です。
データは本人だけが読み書きできるよう設定しています。ログアウトしても、この端末のデータは残ります。</p></section>
<section><h2>出発地の位置の検索</h2>
<p>出発地を保存すると、その文字列を HeartRails Express（駅名の場合）または国土地理院の住所検索（住所の場合）に送り、緯度・経度を調べます。
個人の住所ではなく、最寄駅の登録をおすすめします。</p></section>
<section><h2>外部サービスへの送信</h2>
<p>本サイトは表示や機能のために、次のサービスと通信します。</p>
<dl class="info">
<dt>Google アナリティクス</dt><dd>アクセス解析（上記）</dd>
<dt>Google Fonts</dt><dd>文字の書体の読み込み</dd>
<dt>jsDelivr</dt><dd>同期機能のプログラム（supabase-js）の読み込み（ログイン機能を使うとき）</dd>
<dt>Supabase</dt><dd>端末間の同期（ログインした場合）</dd>
<dt>HeartRails Express・国土地理院</dt><dd>出発地の位置の検索（出発地を保存したとき）</dd>
<dt>Google マップ</dt><dd>「行き方」から経路を開いたとき（出発地と行き先が Google マップに渡ります）</dd>
<dt>広告の提携先</dt><dd>「PR」と表示したリンクを押したとき（提携先が Cookie などで紹介元を記録することがあります）</dd>
</dl></section>
<section><h2>掲載情報について</h2>
<p>開館時間・休館日・料金・展覧会の情報は、各館の公式サイトなどから自動で集めたもので、正確さを保証するものではありません。
お出かけ前に必ず公式サイトでご確認ください。</p></section>
<section><h2>お問い合わせ・改定</h2>
<p>お問い合わせは <a href="https://github.com/riku1128-tong/museum-watch/issues" target="_blank" rel="noopener">GitHub の Issues</a> へお願いします。
このポリシーは必要に応じて改定し、このページに掲載します。</p>
<p class="checked">制定: 2026年9月24日</p></section>"""
    return page(title="プライバシーポリシー｜美術館ウォッチ", desc="美術館ウォッチでのアクセス解析・端末間同期・外部サービスへの送信など、情報の取り扱いについて。",
                path="privacy.html", body=body, depth=0)


def build(active: list[dict], details: dict, days: list[dict], today: date) -> int:
    """全ページと sitemap.xml を作り直す。書き出したページ数を返す。"""
    for sub in ("m", "e", "p", "f"):
        shutil.rmtree(SITE / sub, ignore_errors=True)
        (SITE / sub).mkdir(parents=True)
    by_day = [{r["id"]: r for r in d["results"]} for d in days]
    urls = [("", today.isoformat())]
    n = 0
    for m in active:
        det = details.get(m["id"])
        cal = [(d, by_day[i][m["id"]]) for i, d in enumerate(days)]
        (SITE / "m" / f"{m['id']}.html").write_text(museum_page(m, det, cal, today), encoding="utf-8")
        n += 1
        if not det:
            continue
        urls.append((f"m/{m['id']}.html", det["checked_at"][:10]))
        for e in det["exhibitions"]:
            if e["end"] < today.isoformat():
                continue
            (SITE / "e" / f"{exhibition_id(m['id'], e)}.html").write_text(exhibition_page(m, det, e, today), encoding="utf-8")
            urls.append((f"e/{exhibition_id(m['id'], e)}.html", det["checked_at"][:10]))
            n += 1
    for pref in PREFS:
        ms = [m for m in active if m["prefecture"] == pref]
        if not ms:
            continue
        (SITE / "p" / f"{pref_code(pref)}.html").write_text(prefecture_page(pref, ms, details, by_day[0], today), encoding="utf-8")
        urls.append((f"p/{pref_code(pref)}.html", today.isoformat()))
        n += 1
    (SITE / "privacy.html").write_text(privacy_page(), encoding="utf-8")
    urls.append(("privacy.html", today.isoformat()))
    import extras
    for path in extras.build_features(SITE, active, details, days, today):
        urls.append((path, today.isoformat()))
        n += 1
    (SITE / "about.html").write_text(extras.about_page(), encoding="utf-8")
    (SITE / "disclaimer.html").write_text(extras.disclaimer_page(), encoding="utf-8")
    urls += [("about.html", today.isoformat()), ("disclaimer.html", today.isoformat())]
    xml = "".join(f"<url><loc>{SITE_URL}{escape(u)}</loc><lastmod>{lm}</lastmod></url>" for u, lm in urls)
    (SITE / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{xml}</urlset>\n',
        encoding="utf-8")
    return n
