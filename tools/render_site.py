#!/usr/bin/env python3
"""site/*.fragment.html と nav.json から、公開用の静的サイトを docs/ に組み立てる。

元サイトのURL（例 https://www.unryu.org/home/kotodama）をそのまま保つため、
各ページは docs/home/kotodama/index.html という形で書き出す。こうすると
GitHub Pages でも同じURLでアクセスでき、外部からのリンクが切れない。
"""
import argparse
import html
import json
import os
import re
import shutil
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
DOCS = os.path.join(ROOT, "docs")
ASSETS = os.path.join(ROOT, "assets")
# 旧サイトで配信していた論文PDFなど。中の階層をそのまま docs/ の下に複製する。
# 例 papers/home/papers/xxx.pdf は /home/papers/xxx.pdf として配信される。
PAPERS = os.path.join(ROOT, "papers")

SITE_NAME = "Kazutaka Kurihara"

# このサイトの正規のURL。検索エンジンや共有時に使われる住所である。
# www付きではなく裸のドメインを正規とする。www付きでアクセスした場合は、
# GitHub Pages 側が自動でこちらへ転送する。
CANONICAL = "https://unryu.org"

# 同じ内容を2つのURLで配信しているページの対応表。左が別名、右が正規である。
# 元サイトが / と /home の両方で同じトップページを配信していた名残であり、
# そのまま両方を正規として伝えると、検索エンジンから重複と見なされる。
CANONICAL_ALIASES = {"/home": "/"}

# Google Analytics 4 の測定ID。空文字にすると解析のコードを埋め込まない。
# 手元で試すときや、解析をやめるときは空にする。
GA_MEASUREMENT_ID = "G-VSG5S34B14"

# 公開先によってURLの起点が変わる。
#   独自ドメイン（https://www.unryu.org/）で公開する場合は空文字。
#   GitHub Pages の qurihara.github.io/unryu-site/ で試す場合は "/unryu-site"。
BASE = ""


def canonical_url(path):
    """検索エンジンに正規のURLとして伝える住所を組み立てる。

    ページの実体は docs/home/kotodama/index.html という形で置いてあるため、
    GitHub Pages は /home/kotodama へのアクセスを /home/kotodama/ へ転送する。
    転送される前の形を正規として伝えると、Search Console に
    「ページにリダイレクトがあります」と報告され、クロールが一段分無駄になる。
    そこで、転送されたあとの形、つまり末尾にスラッシュを付けた形を正規とする。
    """
    path = CANONICAL_ALIASES.get(path, path)
    if path == "/":
        return CANONICAL + "/"
    return CANONICAL + path.rstrip("/") + "/"


def robots_snippet(entry):
    """検索エンジンに登録させない指定を組み立てる。

    manifest.json の項目に "noindex": true を書いたページに入る。
    支援者へ直接URLを知らせて読んでいただく案内のように、
    誰でも開けてよいが検索結果には出したくないページのために使う。

    このようなページは sitemap.xml からも外す。載せたまま noindex にすると、
    Search Console が「送信されたURLに noindex タグが追加されています」と
    エラーとして報告するためである。

    robots.txt で拒む方法は採らない。クローラがページを読めなくなり、
    この指定そのものが伝わらなくなる。見比べ用のページ（docs/preview/）で
    同じ判断をしており、そちらは make_theme_previews.py が付けている。
    """
    if not entry.get("noindex"):
        return ""
    return ('<meta name="robots" content="noindex">'
            "<!-- 検索結果には出さない。URLを知る方だけが読む案内 -->\n")


def load_json(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return json.load(fh)


def clean_title(raw_title):
    """「Kazutaka Kurihara - 01. ことだま」からページ名だけを取り出す。"""
    if not raw_title:
        return SITE_NAME
    if " - " in raw_title:
        return raw_title.split(" - ", 1)[1].strip()
    return raw_title.strip()


def nav_html(nav, current_path):
    """サイト共通のナビゲーションを組み立てる。"""
    parts = ['<nav class="site-nav" aria-label="サイト内ナビゲーション">']
    for group in nav:
        children = group["children"]
        if children:
            open_attr = " open" if current_path.startswith(group["href"]) else ""
            parts.append(f"<details class=\"nav-group\"{open_attr}>")
            parts.append(f"<summary>{html.escape(group['title'])}</summary>")
            parts.append("<ul>")
            here = ' aria-current="page"' if current_path == group["href"] else ""
            # そのまとまりの入口へのリンク。英語のページでは英語で書きたいので、
            # nav.json に top_label があればそれを使う
            top_label = group.get("top_label") or f'{group["title"]}のトップ'
            parts.append(
                f'<li><a href="{BASE}{group["href"]}"{here}>'
                f'{html.escape(top_label)}</a></li>'
            )
            for child in children:
                here = ' aria-current="page"' if current_path == child["href"] else ""
                parts.append(
                    f'<li><a href="{BASE}{child["href"]}"{here}>'
                    f"{html.escape(child['label'])}</a></li>"
                )
            parts.append("</ul></details>")
        else:
            here = ' aria-current="page"' if current_path == group["href"] else ""
            parts.append(
                f'<a class="nav-top" href="{BASE}{group["href"]}"{here}>'
                f"{html.escape(group['title'])}</a>"
            )
    parts.append("</nav>")
    return "\n".join(parts)


BLOCK_RE = re.compile(r'<div class="blk">\n(.*?)\n</div>', re.S)

# サムネイルの表示上の高さ。style.css の --thumb-h と同じ値にしておく。
THUMB_HEIGHT = 100
# サムネイルを置く列の幅。style.css の --thumb-w と同じ値にしておく。
# 高さを揃えるとこの幅を超えてしまうほど横長の画像は、説明文の上に置く。
THUMB_COLUMN = 240
# 段組みの右側に置く説明文の長さの上限。
# プロジェクト一覧の説明文は中央値37文字と短く、ページ冒頭の自己紹介文や
# 各プロジェクトの詳細な解説文は数百文字以上ある。この差で両者を見分ける。
THUMB_TEXT_LIMIT = 150


def block_kind(inner):
    """ブロックの中身を見分ける。画像だけのものと、文章を含むものを区別する。"""
    text = re.sub(r"<[^>]+>", "", inner)
    text = html.unescape(text).strip()
    has_img = "<img" in inner
    if has_img and len(text) < 3:
        return "image"
    if has_img:
        return "mixed"
    return "text"


def thumb_display_width(inner):
    """高さを揃えて表示したときの、画像の横幅を求める。

    画像が複数入っている場合は、いちばん横に広くなるものに合わせる。
    """
    widest = 0
    for m in re.finditer(r'<img[^>]*\bwidth="(\d+)"[^>]*\bheight="(\d+)"', inner):
        w, h = int(m.group(1)), int(m.group(2))
        if h:
            widest = max(widest, round(w / h * THUMB_HEIGHT))
    return widest


def compose_layout(body, path=""):
    """プロジェクト紹介の並びを、サムネイル画像と説明文の段組みに組み直す。

    元サイトはプロジェクトを「画像とその説明文」の対で並べている。
    そこで、画像だけのブロックと直後の文章ブロックが対になっている箇所を探す。
    見分け方は2つの条件を組み合わせる。
    ひとつは説明文の長さで、プロジェクト一覧の説明文は短い。これにより、
    ページ冒頭の自己紹介文や、詳細ページの長い解説文を対象から外す。
    もうひとつは対が2つ以上続いていることで、単独で置かれた画像を巻き込まないようにする。

    サムネイルはすべて同じ高さで表示する。高さを揃えると横幅は画像ごとに変わるため、
    列の幅を超えるほど横長の画像については、説明文の上に置いて幅を確保する。
    """
    blocks = [(m.group(1), block_kind(m.group(1))) for m in BLOCK_RE.finditer(body)]
    if not blocks:
        return body

    def text_length(inner):
        return len(html.unescape(re.sub(r"<[^>]+>", "", inner)).strip())

    # 「画像だけのブロック」と「短い文章ブロック」が隣り合う位置を洗い出す
    pair_at = {
        i for i in range(len(blocks) - 1)
        if blocks[i][1] == "image"
        and blocks[i + 1][1] == "text"
        and text_length(blocks[i + 1][0]) <= THUMB_TEXT_LIMIT
    }
    # そのうち、対が続いているものだけを段組みにする
    run_pairs = {i for i in pair_at if (i - 2) in pair_at or (i + 2) in pair_at}

    out = []
    i = 0

    # トップページの冒頭に並ぶ写真（顔写真と書影）は、横に並べて小さく見せる。
    # ここだけは扱いが違うため、まとめてひとつの入れ物に入れる。
    if path in ("/", "/home"):
        lead = 0
        while lead < len(blocks) and blocks[lead][1] == "image":
            lead += 1
        if lead >= 2:
            joined = "\n".join(blocks[j][0] for j in range(lead))
            out.append(f'<div class="header-images">\n{joined}\n</div>')
            i = lead

    while i < len(blocks):
        inner, _kind = blocks[i]
        if i in run_pairs:
            text_inner = blocks[i + 1][0]
            wide = thumb_display_width(inner) > THUMB_COLUMN
            css_class = "thumb-row wide" if wide else "thumb-row"
            out.append(
                f'<div class="{css_class}">\n'
                f'<div class="thumb">{inner}</div>\n'
                f'<div class="thumb-body">{text_inner}</div>\n'
                "</div>"
            )
            i += 2
            continue
        out.append(inner)
        i += 1
    return "\n".join(out)


# サイト内のページのパス一覧。内部リンクに末尾のスラッシュを付けるかどうかの判定に使う。
# main() が manifest.json から埋める。
PAGE_PATHS = set()


def add_trailing_slash(html_text):
    """サイト内のページへのリンクに、末尾のスラッシュを付ける。

    ページの実体は docs/<パス>/index.html なので、GitHub Pages は
    /lab へのアクセスを /lab/ へ転送する。リンクを転送前の形のまま置くと、
    検索エンジンが内部リンクを辿るたびに転送を踏み、Search Console に
    「ページにリダイレクトがあります」として積み上がっていく。

    付けるのは manifest にあるページへのリンクだけである。
    論文PDFや動画などファイルへのリンクは転送が起きないので、そのままにする。
    別リポジトリのプロジェクトサイトも manifest には無いため、触らない。
    """
    def repl(m):
        href = m.group(1)
        if href in PAGE_PATHS and not href.endswith("/"):
            return 'href="%s/"' % href
        return m.group(0)

    return re.sub(r'href="(/[^"#?]*)"', repl, html_text)


def apply_base(body):
    """本文中のサイト内リンクと画像参照に、公開先の起点を付ける。"""
    if not BASE:
        return body
    body = re.sub(r'href="/(?!/)', f'href="{BASE}/', body)
    body = re.sub(r'src="/(?!/)', f'src="{BASE}/', body)
    return body


PAGE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:type" content="website">
<meta property="og:url" content="{canonical_url}">
<link rel="canonical" href="{canonical_url}">
{robots}<link rel="stylesheet" href="{base}/assets/style.css">
{analytics}</head>
<body>
<a class="skip-link" href="#main">本文へ移動</a>
<header class="site-header">
  <a class="site-title" href="{base}/">{site_name}</a>
  <button class="nav-toggle" aria-expanded="false" aria-controls="sitenav">メニュー</button>
</header>
<div class="layout">
  <div class="sidebar" id="sitenav">
{nav}
  </div>
  <main id="main" class="content">
{body}
  </main>
</div>
<footer class="site-footer">
  <p>{site_name} — <a href="{canonical}/">unryu.org</a></p>
</footer>
<script src="{base}/assets/site.js"></script>
</body>
</html>
"""


def analytics_snippet():
    """Google Analytics 4 の計測コードを組み立てる。

    測定IDが空のときは何も返さない。手元で試すときに解析を止められるようにしてある。
    """
    if not GA_MEASUREMENT_ID:
        return ""
    return (
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={GA_MEASUREMENT_ID}"></script>\n'
        "<script>\n"
        "  window.dataLayer = window.dataLayer || [];\n"
        "  function gtag(){dataLayer.push(arguments);}\n"
        "  gtag('js', new Date());\n"
        f"  gtag('config', '{GA_MEASUREMENT_ID}');\n"
        "</script>\n"
    )


def make_description(body_html):
    text = re.sub(r"<[^>]+>", " ", body_html)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return html.escape(text[:150], quote=True)


def fragment_to_docs_path(path):
    """/home/kotodama -> docs/home/kotodama/index.html"""
    if path == "/":
        return os.path.join(DOCS, "index.html")
    return os.path.join(DOCS, path.strip("/"), "index.html")


def main():
    global BASE
    ap = argparse.ArgumentParser(description="静的サイトを docs/ に組み立てる。")
    ap.add_argument(
        "--base", default="",
        help="公開先のURLの起点。独自ドメインなら指定しない。"
             "GitHub Pages で試すときは /リポジトリ名 を渡す。")
    ap.add_argument(
        "--cname", default="",
        help="独自ドメインで公開するときに CNAME ファイルへ書く名前。"
             "例 www.unryu.org。指定しなければ CNAME を作らない。")
    args = ap.parse_args()
    BASE = args.base.rstrip("/")

    manifest = load_json("manifest.json")
    nav = load_json("nav.json")
    PAGE_PATHS.update(e["path"] for e in manifest)

    # docs/ は作り直すが、この仕組みが生成しないものは失わないように退避しておく。
    #   CNAME    GitHub Pages の独自ドメイン設定。消すとドメインの設定が外れ、
    #            進行中の証明書の発行要求もやり直しになる
    #   preview/ 見た目の候補を見比べるためのページ。別の仕組みで作っている
    keep = {}
    for name in ("CNAME", ".nojekyll"):
        path = os.path.join(DOCS, name)
        if os.path.isfile(path):
            keep[name] = open(path, encoding="utf-8").read()
    preview_src = os.path.join(DOCS, "preview")
    preview_tmp = None
    if os.path.isdir(preview_src):
        preview_tmp = tempfile.mkdtemp(prefix="preview-")
        shutil.rmtree(preview_tmp)
        shutil.copytree(preview_src, preview_tmp)

    if os.path.isdir(DOCS):
        shutil.rmtree(DOCS)
    os.makedirs(DOCS, exist_ok=True)

    for name, text in keep.items():
        with open(os.path.join(DOCS, name), "w", encoding="utf-8") as fh:
            fh.write(text)
    if preview_tmp:
        shutil.copytree(preview_tmp, preview_src)
        shutil.rmtree(preview_tmp)

    # 画像などの資産をそのまま複製する
    shutil.copytree(ASSETS, os.path.join(DOCS, "assets"))

    # 論文PDFなどを、papers/ の中の階層のまま docs/ の下へ複製する。
    # docs/ は毎回作り直されるため、ここで置き直さないと失われる。
    if os.path.isdir(PAPERS):
        for dirpath, _dirnames, filenames in os.walk(PAPERS):
            rel = os.path.relpath(dirpath, PAPERS)
            dest_dir = DOCS if rel == "." else os.path.join(DOCS, rel)
            os.makedirs(dest_dir, exist_ok=True)
            for name in filenames:
                if name == ".DS_Store":
                    continue
                shutil.copy2(os.path.join(dirpath, name), os.path.join(dest_dir, name))

    written = 0
    for entry in manifest:
        frag_path = os.path.join(SITE, entry["fragment"])
        if not os.path.exists(frag_path):
            continue
        body = open(frag_path, encoding="utf-8").read()
        body = compose_layout(body, entry["path"])

        title_page = clean_title(entry["title"])
        full_title = SITE_NAME if entry["path"] in ("/", "/home") else f"{title_page} | {SITE_NAME}"
        lang = "en" if entry["path"].startswith("/top-english") else "ja"

        # 見出しが本文の先頭にないページには、ページ名を見出しとして補う
        if entry["path"] not in ("/", "/home") and not re.match(r"\s*<h1", body):
            body = f"<h1>{html.escape(title_page)}</h1>\n" + body

        body = add_trailing_slash(apply_base(body))

        out_html = PAGE.format(
            lang=lang,
            base=BASE,
            canonical=CANONICAL,
            canonical_url=canonical_url(entry["path"]),
            robots=robots_snippet(entry),
            analytics=analytics_snippet(),
            title=html.escape(full_title, quote=True),
            desc=make_description(body),
            path=entry["path"],
            site_name=html.escape(SITE_NAME),
            nav=add_trailing_slash(nav_html(nav, entry["path"])),
            body=body,
        )

        dest = fragment_to_docs_path(entry["path"])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(out_html)
        written += 1

    # 独自ドメインで公開すると決めたときだけ CNAME を置く。
    # DNS を切り替える前にこれを置くと、GitHub Pages が独自ドメインへ誘導しようとして
    # 試験公開用のURLで見られなくなるため、既定では作らない。
    if args.cname:
        with open(os.path.join(DOCS, "CNAME"), "w", encoding="utf-8") as fh:
            fh.write(args.cname.strip() + "\n")
    # Jekyll の処理を通さない
    with open(os.path.join(DOCS, ".nojekyll"), "w", encoding="utf-8") as fh:
        fh.write("")

    # sitemap.xml。検索エンジンには本来のドメインのURLを伝える。
    # 転送されるURLを載せないよう、canonical と同じ組み立て方をそろえる。
    # noindex のページも載せない。載せると Search Console が
    # 「送信されたURLに noindex タグが追加されています」と報告するためである。
    urls = "\n".join(
        f"  <url><loc>{canonical_url(e['path'])}</loc></url>"
        for e in manifest
        if e["path"] not in CANONICAL_ALIASES and not e.get("noindex")
    )
    with open(os.path.join(DOCS, "sitemap.xml"), "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                 f"{urls}\n</urlset>\n")

    with open(os.path.join(DOCS, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"User-agent: *\nAllow: /\n\nSitemap: {CANONICAL}/sitemap.xml\n")

    print(f"{written} ページを {DOCS} に書き出した。")


if __name__ == "__main__":
    main()
