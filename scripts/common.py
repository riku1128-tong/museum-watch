"""スクリプト共通のパス・HTTP セッション・入出力ヘルパー。"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DETAILS = DATA / "details"
DAILY = DATA / "daily"
SITE = ROOT / "docs"  # GitHub Pages の公開元
SCHEMA = ROOT / "schema" / "detail.schema.json"
MUSEUMS_JSON = DATA / "museums.json"

JST = timezone(timedelta(hours=9))

# 公開ページの URL（canonical・sitemap 用）。独自ドメインに移ったら環境変数で上書きする
SITE_URL = os.environ.get("MUSEUM_WATCH_SITE_URL", "https://riku1128-tong.github.io/museum-watch/")
# Google アナリティクス（GA4）の測定 ID。空にすると計測タグを入れない
GA_ID = os.environ.get("MUSEUM_WATCH_GA_ID", "G-NS856TZ0KY")

# 都道府県（JIS コード順）と地方。巡回の優先順は関東 → 近い地域 → 残りをコード順
REGIONS = {
    "北海道": ["北海道"],
    "東北": ["青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県"],
    "関東": ["茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県"],
    "中部": ["新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県"],
    "近畿": ["三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県"],
    "中国": ["鳥取県", "島根県", "岡山県", "広島県", "山口県"],
    "四国": ["徳島県", "香川県", "愛媛県", "高知県"],
    "九州・沖縄": ["福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県"],
}
PREFS = [p for ps in REGIONS.values() for p in ps]
CRAWL_PRIORITY = (["東京都", "神奈川県", "埼玉県", "千葉県", "茨城県", "栃木県", "群馬県", "山梨県", "静岡県", "長野県", "新潟県"]
                  + [p for p in PREFS if p not in {"東京都", "神奈川県", "埼玉県", "千葉県", "茨城県", "栃木県", "群馬県",
                                                   "山梨県", "静岡県", "長野県", "新潟県"}])

# Wikimedia は連絡先（URL かメール）入りの User-Agent でないと 403 を返す。環境変数で上書きできる。
USER_AGENT = "museum-watch/0.1 (personal non-commercial museum-hours digest; {})".format(
    os.environ.get("MUSEUM_WATCH_CONTACT", "https://github.com/riku1128-tong/museum-watch")
)

# Windows のコンソール (cp932) でも日本語を落とさず出す
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def http() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s


def now_jst() -> datetime:
    return datetime.now(JST)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
