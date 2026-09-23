# 美術館ウォッチ（museum-watch）

全国の美術館について、**今日開いているか・何時まで開いているか・何を展示しているか**を一覧で見られるページです。

**ページ: https://riku1128-tong.github.io/museum-watch/**

- 対象: Wikipedia「[美術館の一覧](https://ja.wikipedia.org/wiki/美術館の一覧)」に載っている全国の美術館（544 館。閉館済みの館は除外）。
  公式サイトの巡回は毎回 100 館ずつ、関東 → 近い地域 → 都道府県コード順に広げています。まだ巡回していない館は「情報準備中」として公式サイトへのリンクを表示します
- 更新: 毎週金曜の朝。Claude（Claude Code の定期タスク）が各館の公式サイトを読んで情報を更新します
- 表示: 14 日分。都県・国立/公立/私立・閉館時刻（例: 18 時以降も開いている館）で絞り込めます。館名や展覧会名でも検索できます
- 料金: 大人一般の料金を表示。大人一般が無料になる日（無料開放日）はカードの背景色が変わります
- 会期: 終了 1 週間前から黄色の警告、最終日は赤の警告を表示
- 行った館: カードの「行った」で記録。そのとき開催中の展覧会が終わると自動で未訪問に戻ります（訪問回数は館ごとに残ります）。「今の会期でまだ行っていない館」だけに絞り込めます
- 行きたい: カードの「☆ 行きたい」で美術館ごとにお気に入り登録。「行った」とはどちらか片方だけで、行ったら自動で外れます。「行きたい館」だけに絞り込めます
- 行き方: カードをダブルクリック（スマホは「行き方」）で最寄駅と、設定した出発地からの Google マップ経路（電車）を表示
- 同期: Google でログインすると、行った館と出発地を PC とスマホで同期（準備は [SETUP_FIREBASE.md](SETUP_FIREBASE.md)）

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
uv run scripts/build_list.py                                # 館の一覧を作り直す（全都道府県）
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
