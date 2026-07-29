# 見た目の候補

`assets/style.css` を差し替えるだけで、サイト全体の見た目を切り替えられる。
どの候補も同じクラス名と同じ変数を使うため、HTMLには手を入れなくてよい。

## 候補の一覧

| ファイル | 呼び名 | 方向性 |
| --- | --- | --- |
| `theme-a-notebook.css` | 実験ノート | 方眼紙と等幅の見出しで、測って作る研究の手つきを出す |
| `theme-b-signal.css` | 信号 | 計測機器の画面を思わせる暗い配色。音を扱う研究に寄せる |
| `theme-c-catalogue.css` | 展示カタログ | 明朝の見出しと大きな連番で、美術館の図録のように読ませる |
| `theme-d-refined.css` | 現行版の洗練 | いまの見た目を保ちつつ、文字組みと余白を整える |

## 試す

```bash
cp assets/themes/theme-c-catalogue.css assets/style.css
python3 tools/render_site.py
python3 -m http.server 8791 --directory docs
```

## 元に戻す

```bash
git checkout assets/style.css
```

ベースライン版そのものに戻す場合は次のようにする。

```bash
git checkout baseline-v1 -- assets/style.css
```

## 共通の約束

どの候補でも、次のクラスと変数の意味は変えない。

- 骨組み。`.site-header` `.site-title` `.nav-toggle` `.layout` `.sidebar` `.content` `.site-footer`
- ナビゲーション。`.site-nav` `.nav-group` `.nav-top`
- プロジェクト一覧。`.thumb-row` `.thumb` `.thumb-body`、横長のときは `.thumb-row.wide`
- 冒頭の写真。`.header-images`
- 埋め込みと表。`.embed-wrap` `.table-wrap`
- 大きさの調整。`--thumb-h` `--thumb-w` `--header-img-h`

日本語の文字については、どの候補も端末に入っている書体を指定している。
外部から書体を読み込まないため、表示が速く、配信元が変わっても崩れない。
