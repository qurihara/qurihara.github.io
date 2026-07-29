# unryu.org のクローンサイト

栗原一貴さんの個人ウェブサイト <https://www.unryu.org/> は、現在 Google Sites で作成・管理している。
Google Sites には新版向けの公開APIがなく、AIから直接編集する手段が存在しない。
そこでサイトの内容を取り出し、素のHTML・CSS・JavaScriptで組み直したものがこのリポジトリである。
こうしておくと、AIに「このページのここをこう直して」と平易な言葉で伝えるだけで編集できる。

## いまの状態

- 元サイトの全 57 ページを取り込み済み。本文は合計で約 19 万字。
- 画像 85 点をリポジトリ内に保存済み（`docs/assets/img/`）。外部への依存はない。
- YouTube などの埋め込みは、元の動画をそのまま埋め込む形で残してある。
- 元サイトと同じURL構成を保っている。たとえば `/home/kotodama` は `/home/kotodama` のまま。
  そのため、外部から張られているリンクや検索結果が切れない。

## フォルダの構成

| 場所 | 内容 |
| --- | --- |
| `docs/` | 公開されるサイトそのもの。GitHub Pages はこのフォルダを見る。 |
| `docs/assets/img/` | 取り込んだ画像。 |
| `assets/style.css`、`assets/site.js` | 見た目と動きを決めるファイル。編集はここを直す。 |
| `site/*.fragment.html` | 各ページの本文だけを取り出したもの。文章の編集はここを直す。 |
| `tools/` | 取り込みと組み立てを行うスクリプト。 |
| `raw/` | 元サイトから取得したままのHTML。参照用。 |
| `manifest.json`、`nav.json` | ページ一覧とナビゲーションの定義。 |

## ページの内容を直したいとき

1. `site/` の中の、直したいページに対応するファイルを開く。
   ファイル名はURLに対応している。`/home/kotodama` なら `site/home__kotodama.fragment.html`。
2. 本文を書き換える。ふつうのHTMLなので、段落は `<p>`、見出しは `<h2>` のように書く。
3. 次のコマンドで `docs/` を作り直す。

```bash
python3 tools/render_site.py
```

## 見た目を変えたいとき

`assets/style.css` を編集してから、同じく `python3 tools/render_site.py` を実行する。

## 手元で表示を確かめる

```bash
python3 -m http.server 8791 --directory docs
```

ブラウザで <http://localhost:8791/> を開く。

## 生成物の点検

リンク切れや画像の欠落がないかを調べる。

```bash
python3 tools/check.py
```

## 元サイトから取り込み直したいとき

Google Sites 側を更新した内容をこちらに反映する場合に使う。

```bash
python3 tools/build.py        # 元サイトを取得し、本文と画像を取り込む
python3 tools/nav.py          # ナビゲーションを作り直す（raw/home.html が必要）
python3 tools/render_site.py  # docs/ を組み立てる
```

`tools/build.py` は取得と画像の保存を1つの流れで行う。
Google Sites の画像URLに含まれる印はリクエストごとに変わり、しばらくすると使えなくなるため、
ページの取得と画像の取得を分けられないという事情による。

## 公開の仕方

### 試験公開（GitHub Pages のURLで確認する）

リポジトリ名が `unryu-site` の場合、URLの起点を指定して組み立てる。

```bash
python3 tools/render_site.py --base /unryu-site
```

GitHub のリポジトリ設定の Pages で、公開元を `main` ブランチの `/docs` フォルダにする。
数分後に `https://qurihara.github.io/unryu-site/` で見られるようになる。

### 本公開（unryu.org を向ける）

表示に問題がないと確認できてから行う。

1. 独自ドメイン用に組み立て直す。

```bash
python3 tools/render_site.py --cname www.unryu.org
```

2. GitHub のリポジトリ設定の Pages で、Custom domain に `www.unryu.org` を設定する。
3. ドメインを管理している事業者のDNS設定を、Google Sites 向けから GitHub Pages 向けに変更する。
   - `www` のCNAMEレコードを `qurihara.github.io` に向ける。
   - 裸のドメイン `unryu.org` も使うなら、Aレコードを次の4つに向ける。
     `185.199.108.153` / `185.199.109.153` / `185.199.110.153` / `185.199.111.153`
4. DNSの変更が行き渡るまでに時間がかかる。HTTPSを強制できるようになるまで最大で24時間ほどみておく。

DNSを切り替えるまでは Google Sites 側が生きたままなので、切り戻しもできる。

## 元サイトからの変更点

内容はそのまま保っているが、次の点は作り直しにあたって変わっている。

- Google Sites の段組みのレイアウトは再現していない。画像と文章は上から順に並ぶ。
- 検索窓は付けていない。
- Google Sites が付けていた見出しへのリンクをコピーするボタンは外した。
- 外部リンクがGoogle経由の転送URLになっていたものは、本来のURLに直した。
