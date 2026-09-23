# museum-watch

東京都・神奈川県の美術館（Wikipedia「美術館の一覧」掲載館）について、毎日の開館状況・開館時間・開催中の展示を集めて
`docs/index.html` にまとめるプロジェクト。

## 仕組み
- `scripts/build_list.py`: Wikipedia の wikitext から対象都県の館を抜き出し、Wikidata で公式 URL などを補って `data/museums.json` を作る。
  Wikimedia へのリクエストには連絡先入りの User-Agent が必要（`scripts/common.py`、環境変数 `MUSEUM_WATCH_CONTACT` で上書き）。
- `data/details/<id>.json`: Claude が公式サイトを読んで書く館ごとのルールと例外（開館時間・定休日・祝日ルール・臨時休館・展覧会の会期）。
  形式は `schema/detail.schema.json`。「今日開いているか」は保存しない。
- `scripts/render.py`: 詳細 JSON と日付から開館・休館を決定的に計算する（祝日は jpholiday）。
  `docs/index.html`（14 日分。ページを開いた日を今日として表示）と `data/daily/YYYY-MM-DD.json` を出す。HTML の元は `scripts/template.html`。
- `scripts/plan_run.py`: 各館を full / light / skip のどれで確認するか決め、バッチに分ける。
- `prompts/daily_update.md`: 毎週金曜 6:00 の定期タスク（Claude デスクトップアプリ）が従う手順書。

## コマンド
```bash
uv run scripts/build_list.py --prefectures 東京都,神奈川県
uv run scripts/plan_run.py
uv run scripts/validate.py [id ...]
uv run scripts/render.py [--date YYYY-MM-DD] [--print]
uv run pytest -q
```

## ルール
- 「不明」を残さない。公式サイトが読めなければ、別ページ・検索・自治体ページ・美術情報サイトの順に当たり、`plan_run.py --retry` で再挑戦する。
- ただし詳細 JSON に、推測した日付や時刻は入れない。どうしても読めなかった項目だけ `unknown` にするか、`confidence` を下げる。
- 判定ロジックを変えたら `tests/test_render.py` にケースを足す。
- 定期タスクがコミットしてよいのは `data/` と `docs/` だけ（検証が通ったときに main へプッシュし、GitHub Pages を更新する）。
- 公開ページ: https://riku1128-tong.github.io/museum-watch/
