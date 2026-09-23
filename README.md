# 美術館ウォッチ（museum-watch）

東京都・神奈川県の美術館について、**今日開いているか・何時まで開いているか・何を展示しているか**を一覧で見られるページです。

**ページ: https://riku1128-tong.github.io/museum-watch/**

- 対象: Wikipedia「[美術館の一覧](https://ja.wikipedia.org/wiki/美術館の一覧)」に載っている東京都・神奈川県の美術館（76 館。閉館済みの館は除外）
- 更新: 毎週金曜の朝。Claude（Claude Code の定期タスク）が各館の公式サイトを読んで情報を更新します
- 表示: 14 日分。都県・国立/公立/私立・閉館時刻（例: 18 時以降も開いている館）で絞り込めます。館名や展覧会名でも検索できます

> 情報は公式サイトから自動で集めたものです。臨時休館などが反映されていないことがあるので、出かける前に公式サイトで確認してください。

## 仕組み

```
Wikipedia/Wikidata ──build_list.py──▶ data/museums.json（館の一覧・公式URL）
公式サイト ──Claude（prompts/daily_update.md）──▶ data/details/<id>.json（開館時間・休館日のルール、臨時休館、展覧会の会期）
data/details ──render.py（祝日は jpholiday）──▶ docs/index.html ＋ data/daily/YYYY-MM-DD.json
```

「今日開いているか」は Claude に直接答えさせません。開館時間・定休日（第n週も可）・祝日ルール（祝日なら開館して翌平日を休館、など）・臨時休館・展示替えをデータとして保存し、日ごとの開館・休館は `render.py` がそのデータから計算します。

## 使い方

[uv](https://docs.astral.sh/uv/) が必要です。

```bash
uv sync
uv run scripts/build_list.py --prefectures 東京都,神奈川県   # 館の一覧を作り直す
uv run scripts/plan_run.py                                  # 巡回計画（full / light / skip）
uv run scripts/validate.py                                  # 詳細 JSON の検証
uv run scripts/render.py                                    # docs/index.html を生成
uv run scripts/render.py --date 2026-10-12 --print          # 指定日の判定を表で確認
uv run pytest -q
```

Wikimedia の API には連絡先入りの User-Agent が必要です。フォークして使う場合は、環境変数 `MUSEUM_WATCH_CONTACT` に自分の連絡先（URL かメールアドレス）を設定してください。

## データの出典

- 館の一覧: Wikipedia（CC BY-SA 4.0）、Wikidata（CC0）
- 開館時間・展覧会: 各美術館の公式サイト（リンクはページ上の館名と `data/details/*.json` の `source_urls`）
