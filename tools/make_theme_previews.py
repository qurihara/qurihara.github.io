#!/usr/bin/env python3
"""見た目の候補を見比べるためのページを docs/preview/ に作る。

同じ内容のページに対して、読み込む見た目のファイルだけを差し替えたものを並べる。
画像は本体と同じものを参照するため、置き場所が増えても容量はほとんど変わらない。
"""
import html
import os
import re
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")
THEMES_SRC = os.path.join(ROOT, "assets", "themes")
PREVIEW = os.path.join(DOCS, "preview")

# 候補の一覧。ファイル名、呼び名、ねらいの説明。
THEMES = [
    ("theme-a-notebook", "候補A 実験ノート",
     "方眼紙と等幅の標識で、測って作る研究の手つきを出す。差し色は製図用のインクの青。"),
    ("theme-b-signal", "候補B 信号",
     "計測機器の画面に見立てた暗い配色。差し色は古い計器の琥珀色。暗い配色ひとつで通す。"),
    ("theme-c-catalogue", "候補C 展示カタログ",
     "見出しを明朝にして図録のように読ませる。差し色は藍。番号を作品目録として使う。"),
    ("theme-d-refined", "候補D 現行版の洗練",
     "いまの見た目のまま、差し色と行長、見出しの段差、余白を整える。変化はいちばん小さい。"),
]

# 見比べる対象のページ
SAMPLES = [
    ("/", "index.html", "トップページ"),
    ("/home/speechjammer", "home/speechjammer/index.html", "プロジェクトのページ"),
    ("/publications", "publications/index.html", "業績一覧"),
]


def build_variant(src_html, theme_key, base_depth):
    """ページの見た目のファイルへの参照を、候補のものに差し替える。"""
    up = "../" * base_depth
    s = src_html
    s = s.replace('href="/assets/style.css"',
                  f'href="/assets/themes/{theme_key}.css"')
    # 候補を見比べていることが分かる帯を、本文の先頭に足す
    banner = (
        '<div style="position:sticky;top:0;z-index:60;background:#111;color:#fff;'
        'font:14px/1.6 system-ui,sans-serif;padding:9px 16px;display:flex;'
        'gap:14px;flex-wrap:wrap;align-items:center">'
        f'<strong style="font-weight:600">{html.escape(theme_key)}</strong>'
        f'<a href="{up}preview/" style="color:#8ab4f8">候補の一覧へ戻る</a>'
        "</div>"
    )
    s = s.replace("<body>", "<body>\n" + banner, 1)
    return s


def main():
    if not os.path.isdir(DOCS):
        raise SystemExit("先に python3 tools/render_site.py を実行する")

    # 候補のCSSを公開側にも置く
    dst_themes = os.path.join(DOCS, "assets", "themes")
    os.makedirs(dst_themes, exist_ok=True)
    for key, _name, _desc in THEMES:
        shutil.copy(os.path.join(THEMES_SRC, key + ".css"),
                    os.path.join(dst_themes, key + ".css"))

    if os.path.isdir(PREVIEW):
        shutil.rmtree(PREVIEW)
    os.makedirs(PREVIEW, exist_ok=True)

    made = 0
    for key, name, _desc in THEMES:
        for _path, rel, _label in SAMPLES:
            src = os.path.join(DOCS, rel)
            if not os.path.exists(src):
                continue
            page = open(src, encoding="utf-8").read()
            out_rel = os.path.join(key, rel)
            dest = os.path.join(PREVIEW, out_rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            depth = out_rel.count(os.sep) + 1
            with open(dest, "w", encoding="utf-8") as fh:
                fh.write(build_variant(page, key, depth))
            made += 1

    # 候補の一覧ページ
    cards = []
    for key, name, desc in THEMES:
        links = " ／ ".join(
            f'<a href="{key}/{rel.replace("index.html", "") or ""}">{html.escape(label)}</a>'
            for _p, rel, label in SAMPLES
        )
        cards.append(
            '<section style="border-top:1px solid #ddd;padding:18px 0">'
            f'<h2 style="margin:0 0 6px;font-size:1.15rem">{html.escape(name)}</h2>'
            f'<p style="margin:0 0 10px;color:#555">{html.escape(desc)}</p>'
            f'<p style="margin:0">{links}</p>'
            "</section>"
        )

    index = f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>見た目の候補を見比べる</title>
<style>
  body {{ margin:0; background:#fff; color:#1b2026;
    font-family:"Hiragino Kaku Gothic ProN","Hiragino Sans","Yu Gothic",Meiryo,system-ui,sans-serif;
    line-height:1.85; }}
  main {{ max-width:720px; margin:0 auto; padding:36px 22px 90px; }}
  h1 {{ font-size:1.5rem; margin:0 0 10px; }}
  a {{ color:#1558b0; }}
  .lead {{ color:#555; margin:0 0 22px; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background:#14181c; color:#e6eaee; }}
    .lead, section p {{ color:#96a1ac !important; }}
    section {{ border-top-color:#2a3037 !important; }}
    a {{ color:#82b4f7; }}
  }}
</style></head>
<body><main>
<h1>見た目の候補を見比べる</h1>
<p class="lead">同じ内容のページを、4つの見た目で表示したものである。
画面の幅を変えると、狭い画面での表示も確かめられる。
どれを採用しても、文章と画像そのものは変わらない。</p>
{"".join(cards)}
<section style="border-top:1px solid #ddd;padding:18px 0">
<h2 style="margin:0 0 6px;font-size:1.15rem">いまのサイト</h2>
<p style="margin:0"><a href="/">現在の見た目のトップページ</a></p>
</section>
</main></body></html>
"""
    with open(os.path.join(PREVIEW, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(index)

    size = sum(
        os.path.getsize(os.path.join(dp, f))
        for dp, _dn, fn in os.walk(PREVIEW) for f in fn
    )
    print(f"見比べ用に {made} ページを作った。{PREVIEW}")
    print(f"追加される容量は {size // 1024} KB（画像は本体と共用するため増えない）")


if __name__ == "__main__":
    main()
