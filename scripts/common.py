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
