"""お問い合わせフォーム（Google フォーム）。data/contact.json の form_url を入れると、次の場所に出る。

    about.html            お問い合わせフォームへのボタン（GitHub の Issues は予備として残す）
    m/ e/ の各ページ      「掲載内容の誤りを報告する」リンク
    privacy.html          外部サービスに Google フォームを追加

prefill_entry に Google フォームの「事前入力した URL」の entry.〇〇 を入れると、
報告リンクから開いたときに館名・展覧会名が最初から入る（空なら入らないだけで、フォームは開ける）。
"""

from __future__ import annotations

import json
from html import escape
from urllib.parse import quote

from common import DATA

CONFIG = DATA / "contact.json"


def load() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}


def form_url(subject: str = "") -> str | None:
    c = load()
    url = c.get("form_url")
    if not url:
        return None
    if subject and c.get("prefill_entry"):
        url += f"{'&' if '?' in url else '?'}usp=pp_url&{c['prefill_entry']}={quote(subject)}"
    return url


def report_html(subject: str) -> str:
    """館・展覧会のページの末尾に置く報告リンク。フォームが未設定なら何も出さない。"""
    url = form_url(subject)
    if not url:
        return ""
    return (f'<p class="checked"><a href="{escape(url)}" target="_blank" rel="noopener">'
            f'掲載内容の誤りを報告する</a>（お問い合わせフォームが開きます）</p>')
