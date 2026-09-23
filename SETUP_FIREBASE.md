# Firebase の準備（ログインとスマホ同期）

「行った館」と「出発地」を、Google ログインで PC とスマホの間で同期するための準備です。
所要時間は 10 分ほどで、Firebase の無料プラン（Spark）の範囲で動きます。

## 1. プロジェクトを作る
1. https://console.firebase.google.com を開き、「プロジェクトを作成」
2. プロジェクト名は `museum-watch` など。Google アナリティクスはオフでよい

## 2. Google ログインを有効にする
1. 左メニュー「構築」→「Authentication」→「始める」
2. 「Sign-in method」タブ →「Google」を選んで「有効にする」→ サポートメールを選んで保存
3. 「設定」タブ →「承認済みドメイン」→「ドメインを追加」→ `riku1128-tong.github.io` を追加
   （`localhost` は最初から入っています）

## 3. データベース（Firestore）を作る
1. 左メニュー「構築」→「Firestore Database」→「データベースを作成」
2. ロケーションは `asia-northeast1`（東京）、モードは「本番環境モード」
3. 「ルール」タブを開き、このリポジトリの [firestore.rules](firestore.rules) の中身に置き換えて「公開」
   （自分のデータだけを読み書きできるルールです）

## 4. Web アプリを登録して設定をコピーする
1. 左上の歯車 →「プロジェクトの設定」→「マイアプリ」→ ウェブ（`</>`）アイコン
2. アプリのニックネームを入れて登録（Firebase Hosting のチェックは不要）
3. 表示される `firebaseConfig = { apiKey: ..., authDomain: ..., projectId: ..., ... }` をコピー

## 5. ページに設定を入れる
[docs/firebase-config.js](docs/firebase-config.js) の `null` を、コピーした設定に置き換えます。

```js
window.FIREBASE_CONFIG = {
  apiKey: "...",
  authDomain: "museum-watch-xxxx.firebaseapp.com",
  projectId: "museum-watch-xxxx",
  storageBucket: "...",
  messagingSenderId: "...",
  appId: "...",
};
```

コミットしてプッシュすれば、公開ページの設定画面（右上の歯車）に「Google でログイン」が出ます。
Claude に設定を渡してもらえれば、こちらで書き換えてプッシュします。

### 補足
- `firebaseConfig` の `apiKey` は、公開ページに載せる前提の識別子です（秘密鍵ではありません）。
  データは手順 3 のルールで守られます。
- 念のため Google Cloud コンソールの「API とサービス」→「認証情報」で、この API キーの
  「ウェブサイトの制限」に `https://riku1128-tong.github.io/*` を設定しておくと、よそのサイトから使われなくなります。
- 保存される内容は、訪問記録（館の ID・訪問日・そのとき開催中だった展覧会の会期末）・出発地の文字列・更新時刻だけです。出発地は住所より最寄駅の登録がおすすめです。
