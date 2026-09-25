"""運営者情報・免責事項と、巡回データから毎週作り直す特集ページ（docs/f/）。pages.build から呼ばれる。

特集:
    f/index.html     特集の一覧
    f/ending.html    会期終了間近の展覧会（今日から 2 週間以内に終わる）
    f/upcoming.html  これから始まる展覧会（今日から 30 日以内に始まる）
    f/free.html      無料開放日カレンダー（今日から 6 週間）
    f/late.html      夜遅くまで開いている美術館（今日から 2 週間、19 時以降も開いている日）
"""

from __future__ import annotations

from datetime import date, timedelta
from html import escape

from common import REGIONS
from pages import FREE_SCOPE, exhibition_id, md, page, yen
from render import exhibition_price, free_on

REGION_OF = {p: r for r, ps in REGIONS.items() for p in ps}
WEEK = "月火水木金土日"
LATE = "19:00"

FEATURES = [
    ("ending", "会期終了間近の展覧会", "今日から 2 週間以内に終わる展覧会。見逃す前に。"),
    ("upcoming", "これから始まる展覧会", "今日から 30 日以内に始まる展覧会。"),
    ("free", "無料開放日カレンダー", "大人一般が無料になる日（常設展だけ・一部だけの無料も含む）を 6 週間先まで。"),
    ("late", "夜遅くまで開いている美術館", "19 時以降も開いている日と館。仕事帰りに。"),
]


def label(d: date) -> str:
    return f"{d.month}/{d.day}（{WEEK[d.weekday()]}）"


def by_region(items: list[tuple[str, str]]) -> str:
    """(都道府県, HTML) の並びを地方ごとの見出しでまとめる。"""
    out = []
    for region, prefs in REGIONS.items():
        rows = [html for pref, html in items if pref in prefs]
        if rows:
            out.append(f'<section><h2>{escape(region)}</h2><ul class="ex">{"".join(rows)}</ul></section>')
    return "".join(out) or '<section><p>今は該当する展覧会・館がありません。毎週更新しています。</p></section>'


def ex_row(m: dict, e: dict, note: str, today: date) -> str:
    price = exhibition_price(e)
    meta = " ・ ".join(x for x in [note, f"{md(e['start'], today)} – {md(e['end'], today)}",
                                   f"一般 {yen(price)}" if price is not None else ""] if x)
    return (f'<li class="{"special" if e.get("kind") == "special" else ""}">'
            f'<div class="ex-title"><a href="../e/{exhibition_id(m["id"], e)}.html">{escape(e["title"])}</a></div>'
            f'<div class="ex-meta"><span><a href="../m/{m["id"]}.html">{escape(m["name"])}</a>（{escape(m["prefecture"])}）</span><span>{meta}</span></div>'
            f'{f"<div class=ex-rec><b>おすすめ</b> {escape(e["recommend"])}</div>" if e.get("recommend") else ""}</li>')


def feature_page(key: str, title: str, lead: str, body: str, today: date) -> str:
    nav = " ／ ".join(f'<a href="{k}.html">{escape(t)}</a>' for k, t, _ in FEATURES if k != key)
    return page(title=f"{title}（{today.month}/{today.day}更新）｜美術館ウォッチ", desc=f"{lead}毎週更新。",
                path=f"f/{key}.html", depth=1,
                body=(f'<nav class="crumbs"><a href="../index.html">全国</a> › <a href="index.html">特集</a> › {escape(title)}</nav>'
                      f'<h1>{escape(title)}</h1><p class="lead">{escape(lead)}（{label(today)}時点）</p>{body}'
                      f'<p class="checked">ほかの特集: {nav}</p>'))


def build_features(site, active: list[dict], details: dict, days: list[dict], today: date) -> list[str]:
    """特集ページを書き出し、sitemap 用のパスを返す。"""
    (site / "f").mkdir(exist_ok=True)
    t = today.isoformat()
    museums = [(m, details[m["id"]]) for m in active if m["id"] in details]

    # 会期終了間近
    limit = (today + timedelta(days=14)).isoformat()
    ending = sorted(((m, e) for m, det in museums for e in det["exhibitions"] if t <= e["end"] <= limit and e["start"] <= t),
                    key=lambda x: x[1]["end"])
    ending_html = by_region([(m["prefecture"], ex_row(m, e, "本日最終日" if e["end"] == t else
                                                      f"あと{(date.fromisoformat(e['end']) - today).days}日", today)) for m, e in ending])

    # これから始まる
    limit = (today + timedelta(days=30)).isoformat()
    upcoming = sorted(((m, e) for m, det in museums for e in det["exhibitions"] if t < e["start"] <= limit),
                      key=lambda x: x[1]["start"])
    upcoming_html = by_region([(m["prefecture"], ex_row(m, e, f"{md(e['start'])}から", today)) for m, e in upcoming])

    # 無料開放日（6 週間）
    free_sections = []
    for i in range(42):
        d = today + timedelta(days=i)
        rows = []
        for m, det in museums:
            f = free_on(det, d)
            if not f:
                continue
            what = FREE_SCOPE[f["scope"]] + (f"（{'・'.join(f.get('targets', []))}）" if f.get("targets") else "")
            rows.append(f'<li><div class="ex-title"><a href="../m/{m["id"]}.html">{escape(m["name"])}</a></div>'
                        f'<div class="ex-meta">{escape(m["prefecture"])} ・ {escape(what)}{" ・ " + escape(f["reason"]) if f.get("reason") else ""}</div></li>')
        if rows:
            free_sections.append(f'<section><h2>{label(d)}</h2><ul class="ex">{"".join(rows)}</ul></section>')
    free_html = "".join(free_sections) or '<section><p>6 週間先までに、わかっている無料開放日はまだありません。毎週更新しています。</p></section>'
    free_html += '<p class="checked">休館日と重なる場合があります。お出かけ前に各館のページの開館カレンダーもご確認ください。</p>'

    # 夜遅くまで（2 週間）
    late_sections = []
    for day in days:
        rows = [r for r in day["results"] if r["status"] == "open" and r.get("close") and r["close"] >= LATE]
        if not rows:
            continue
        rows.sort(key=lambda r: r["close"], reverse=True)
        names = {m["id"]: m for m in active}
        items = "".join(f'<li><div class="ex-title"><a href="../m/{r["id"]}.html">{escape(names[r["id"]]["name"])}</a></div>'
                        f'<div class="ex-meta">{escape(names[r["id"]]["prefecture"])} ・ {r["open"]}–{r["close"]}'
                        f'{" ・ " + escape(r["exhibitions"][0]["title"]) if r.get("exhibitions") else ""}</div></li>' for r in rows)
        late_sections.append(f'<section><h2>{label(date.fromisoformat(day["date"]))}</h2><ul class="ex">{items}</ul></section>')
    late_html = "".join(late_sections) or '<section><p>2 週間以内に 19 時以降も開いている館はまだ見つかっていません。</p></section>'

    bodies = {"ending": ending_html, "upcoming": upcoming_html, "free": free_html, "late": late_html}
    counts = {"ending": len(ending), "upcoming": len(upcoming), "free": len(free_sections), "late": len(late_sections)}
    paths = []
    for key, title, lead in FEATURES:
        (site / "f" / f"{key}.html").write_text(feature_page(key, title, lead, bodies[key], today), encoding="utf-8")
        paths.append(f"f/{key}.html")
    unit = {"ending": "件", "upcoming": "件", "free": "日", "late": "日"}
    cards = "".join(f'<li><div class="ex-title"><a href="{k}.html">{escape(t)}</a></div>'
                    f'<div class="ex-meta">{escape(lead)} ・ {counts[k]}{unit[k]}</div></li>' for k, t, lead in FEATURES)
    (site / "f" / "index.html").write_text(page(
        title="特集｜美術館ウォッチ", desc="会期終了間近の展覧会、これから始まる展覧会、無料開放日、夜遅くまで開いている美術館。毎週更新。",
        path="f/index.html", depth=1,
        body=(f'<nav class="crumbs"><a href="../index.html">全国</a> › 特集</nav><h1>特集</h1>'
              f'<p class="lead">美術館ウォッチの巡回データから、毎週自動で作っています（{label(today)}時点）。</p>'
              f'<section><ul class="ex">{cards}</ul></section>')), encoding="utf-8")
    paths.append("f/index.html")
    return paths


def about_page() -> str:
    body = """<h1>運営者情報・お問い合わせ</h1>
<section><h2>このサイトについて</h2>
<p>美術館ウォッチは、全国の美術館の開館状況・開館時間・料金・開催中の展覧会を、ひと目で探せるようにする個人運営のサイトです。
Wikipedia「美術館の一覧」に載っている美術館を対象に、各館の公式サイトの情報を毎週自動で集めて更新しています。</p></section>
<section><h2>運営者</h2>
<dl class="info">
<dt>サイト名</dt><dd>美術館ウォッチ</dd>
<dt>運営</dt><dd>個人（GitHub: <a href="https://github.com/riku1128-tong" target="_blank" rel="noopener">riku1128-tong</a>）</dd>
<dt>開始</dt><dd>2026年9月</dd>
<dt>ソースコード</dt><dd><a href="https://github.com/riku1128-tong/museum-watch" target="_blank" rel="noopener">GitHub で公開しています</a></dd>
</dl></section>
<section><h2>お問い合わせ</h2>
<p>掲載内容の誤り・修正のご依頼、ご意見は、<a href="https://github.com/riku1128-tong/museum-watch/issues" target="_blank" rel="noopener">GitHub の Issues</a>
からお送りください。美術館の関係者の方からの、掲載情報の訂正や掲載停止のご依頼も受け付けています。</p></section>
<section><h2>情報の集め方</h2>
<p>開館時間・休館日・料金・展覧会の情報は、AI（Anthropic 社の Claude）が各館の公式サイトを読んで集め、決まった形に整えています。
館の「見どころ」と展覧会の「おすすめポイント」も、公式サイトの情報をもとに AI が要約したものです。
詳しくは<a href="disclaimer.html">免責事項</a>をご覧ください。</p></section>"""
    return page(title="運営者情報・お問い合わせ｜美術館ウォッチ", desc="美術館ウォッチの運営者情報とお問い合わせ先、情報の集め方について。",
                path="about.html", body=body, depth=0)


def disclaimer_page() -> str:
    body = """<h1>免責事項</h1>
<section><h2>掲載情報について</h2>
<p>本サイトの開館時間・休館日・料金・展覧会・無料開放日・最寄駅などの情報は、各館の公式サイトなどから自動で集めたものです。
集めた時点から変更されていたり、読み取りの誤りがあったりする場合があります。正確さ・完全さ・最新であることは保証できません。
お出かけ前に、必ず各館の公式サイトで最新の情報をご確認ください。</p>
<p>「開館」「休館」の表示は、集めた開館時間・休館日のきまりと臨時休館の情報から計算したものです。
臨時休館、混雑による入場制限、予約制などが反映されていない場合があります。</p></section>
<section><h2>AI による要約について</h2>
<p>館の「見どころ」と展覧会の「おすすめポイント」は、公式サイトの情報をもとに AI が作成した要約です。
内容の正確さは保証できません。展示の内容や作品の詳細は、各館の公式情報をご確認ください。</p></section>
<section><h2>出発地からの距離・行き方について</h2>
<p>「出発地から近い順」の距離は直線距離の目安です。実際の経路や所要時間は、「行き方」から開く Google マップなどでご確認ください。</p></section>
<section><h2>損害について</h2>
<p>本サイトの情報を利用したことで生じたいかなる損害についても、運営者は責任を負いかねます。</p></section>
<section><h2>リンク・広告について</h2>
<p>本サイトから外部サイトへのリンク先の内容について、運営者は責任を負いません。
本サイトは、アフィリエイトプログラムなどの広告を掲載する場合があります。その場合は「PR」と表示します。</p></section>
<section><h2>著作権について</h2>
<p>館の一覧は Wikipedia（CC BY-SA 4.0）と Wikidata のデータを使っています。展覧会の名称などの権利は各館・各主催者に帰属します。
本サイトは各館の画像やポスターを転載していません。</p>
<p class="checked">制定: 2026年9月26日</p></section>"""
    return page(title="免責事項｜美術館ウォッチ", desc="美術館ウォッチの掲載情報・AI による要約・広告についての免責事項。",
                path="disclaimer.html", body=body, depth=0)
