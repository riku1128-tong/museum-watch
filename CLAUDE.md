# museum-watch

全国の美術館（Wikipedia「美術館の一覧」掲載館）について、毎日の開館状況・開館時間・開催中の展示を集めて
`docs/index.html` にまとめるプロジェクト。

## 仕組み
- `scripts/build_list.py`: Wikipedia の wikitext から対象都県の館を抜き出し、Wikidata で公式 URL などを補って `data/museums.json` を作る。
  Wikimedia へのリクエストには連絡先入りの User-Agent が必要（`scripts/common.py`、環境変数 `MUSEUM_WATCH_CONTACT` で上書き）。
- `data/details/<id>.json`: Claude が公式サイトを読んで書く館ごとのルールと例外（開館時間・定休日・祝日ルール・臨時休館・展覧会の会期）。
  形式は `schema/detail.schema.json`。「今日開いているか」は保存しない。
- `scripts/render.py`: 詳細 JSON と日付から開館・休館を決定的に計算する（祝日は jpholiday）。
  `docs/index.html`（14 日分。ページを開いた日を今日として表示）と `data/daily/YYYY-MM-DD.json` を出す。HTML の元は `scripts/template.html`。
- `scripts/plan_run.py`: 各館を full / light / skip のどれで確認するか決め、バッチに分ける。まだ巡回していない館は 1 回 100 館まで（`--max-new`）、`common.CRAWL_PRIORITY` の順（関東 → 近い地域 → コード順）。
- `scripts/template.html`: 公開ページ。大理石の背景画像（`docs/marble-*.jpg`）は `scripts/marble_bake.html` を ブラウザで開いて焼き付ける（受け取り役は `scripts/marble_upload.py`）。
- 訪問記録・行きたい館・出発地はブラウザの localStorage に保存し、Supabase（メールのコードでログイン）で端末間同期する。接続先は `docs/sync-config.js`（publishable key。グルメレコメンドアプリと同じプロジェクトに相乗り）、テーブルは `museum_watch_state`（`supabase/museum_watch.sql`、RLS で自分の行だけ）。ログイン状態の保存キーは同じ github.io の別アプリと分けている。
- `scripts/pages.py`: 検索から人が来るための静的ページ（`docs/m/` 館、`docs/e/` 展覧会、`docs/p/` 都道府県）と `docs/sitemap.xml` を作る。render.py の最後に呼ばれ、毎回作り直す。未巡回の館のページは noindex。CSS は `scripts/style.css`（トップページと共通）。
- `prompts/daily_update.md`: 毎週金曜 6:00 の定期タスク（Claude デスクトップアプリ）が従う手順書。

## 計測（GA4）
- 測定 ID は `common.GA_ID`（環境変数 `MUSEUM_WATCH_GA_ID`）。localhost では読み込まない。
- イベント: `want_toggle` / `visit_toggle`（`state` = on/off）、`route_open`、`route_map_click`（`map_type` = from_origin/place）、`filter_change`（`filter_name` / `filter_value`）、`login`、キーイベント用に付けたときだけ送る `want_add` / `visit_add`。館のイベントには `museum_id` / `museum_name` を付ける。`value` は GA4 の予約パラメータ（金額）なので使わない。GA4 側でこれらをイベント範囲のカスタムディメンションとして登録済みの前提。出発地・メールアドレス・訪問記録は送らない。
- 外部サイトへのリンクだけに UTM を付ける（`utm_source=museum-watch`、`utm_campaign` = 置き場所、`utm_content` = 館 ID）。サイト内のリンクには付けない（GA4 の流入元が上書きされるため）。

## コマンド
```bash
uv run scripts/build_list.py            # 全都道府県（--prefectures 東京都,千葉県 で絞れる）
uv run scripts/plan_run.py
uv run scripts/validate.py [id ...]
uv run scripts/render.py [--date YYYY-MM-DD] [--print]
uv run pytest -q
```

## ルール
- 「不明」を残さない。公式サイトが読めなければ、別ページ・検索・自治体ページ・美術情報サイトの順に当たり、`plan_run.py --retry` で再挑戦する。
- ただし詳細 JSON に、推測した日付や時刻は入れない。どうしても読めなかった項目だけ `unknown` にするか、`confidence` を下げる。
- 判定ロジックを変えたら `tests/test_render.py` にケースを足す。
- 無料開放日は、館ごとの巡回に加えて、毎回の巡回で都道府県などの無料イベント（県民の日・関西文化の日・国際博物館の日など）を 6 週間先まで調べる（手順書 1.5）。
- 定期タスクがコミットしてよいのは `data/` と `docs/` だけ（検証が通ったときに main へプッシュし、GitHub Pages を更新する）。
- 公開ページ: https://riku1128-tong.github.io/museum-watch/
