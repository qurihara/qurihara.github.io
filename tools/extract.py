#!/usr/bin/env python3
"""raw/ に保存したGoogle SitesのHTMLから本文を取り出し、site/ に素のHTMLとして書き出す。

Google Sites の本文は role="main" の div の中にある。その中身は見出し・段落・リンク・
画像・埋め込みといった標準的なHTMLタグで表現されているため、Googleの内部用属性や
装飾用のノイズを取り除けば、そのまま編集しやすいHTMLになる。
"""
import html
import json
import os
import re
import sys
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")
SITE = os.path.join(ROOT, "site")

# 残す属性。これ以外はGoogleの内部制御用なので落とす。
KEEP_ATTRS = {"href", "src", "alt", "title", "colspan", "rowspan", "target", "rel",
              "width", "height"}

# 本文として意味のあるタグだけを通す。
ALLOWED = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "a", "img", "br", "hr",
    "strong", "b", "em", "i", "u", "s", "sub", "sup",
    "blockquote", "pre", "code",
    "table", "thead", "tbody", "tr", "td", "th",
    "div", "span", "section", "iframe", "figure", "figcaption",
}

# 中身ごと捨てるタグ
DROP_TREE = {"script", "style", "svg", "noscript", "button"}


class MainExtractor(HTMLParser):
    """本文ブロックの div を、入れ子の深さを数えながら切り出す。

    Google Sites は本文の各ブロックを class="tyJCtd ..." の div に入れる。
    ページ全体で role="main" は1個しかないため、こちらを目印にする。
    """

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.capturing = False
        self.depth = 0
        self.chunks = []
        self.results = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if not self.capturing:
            if tag == "div" and "tyJCtd" in (d.get("class") or "").split():
                self.capturing = True
                self.depth = 1
                self.chunks = []
            return
        if tag == "div":
            self.depth += 1
        if tag not in ("br", "img", "hr", "input", "meta", "link"):
            self.chunks.append(("start", tag, d))
        else:
            self.chunks.append(("void", tag, d))

    def handle_endtag(self, tag):
        if not self.capturing:
            return
        if tag == "div":
            self.depth -= 1
            if self.depth == 0:
                self.capturing = False
                self.results.append(self.chunks)
                self.chunks = []
                return
        self.chunks.append(("end", tag, None))

    def handle_data(self, data):
        if self.capturing:
            self.chunks.append(("text", None, data))

    def handle_entityref(self, name):
        if self.capturing:
            self.chunks.append(("text", None, html.unescape("&" + name + ";")))

    def handle_charref(self, name):
        if self.capturing:
            self.chunks.append(("text", None, html.unescape("&#" + name + ";")))


def render(chunks):
    """切り出したチャンク列を、ノイズを落としたHTML文字列に組み立てる。

    開いたタグを積み上げて管理し、対応する開始タグのない終了タグは捨てる。
    最後まで閉じられなかったタグはここで閉じる。こうしないと、余った </div> が
    ページ側のレイアウト用の要素を閉じてしまい、表示が崩れる。
    """
    out = []
    drop_depth = 0
    drop_tag = None
    stack = []          # 実際に出力した開始タグ
    skipped = []        # 出力しなかった開始タグ（中身だけ活かすもの）

    for kind, tag, payload in chunks:
        if drop_depth > 0:
            if kind == "start" and tag == drop_tag:
                drop_depth += 1
            elif kind == "end" and tag == drop_tag:
                drop_depth -= 1
                if drop_depth == 0:
                    drop_tag = None
            continue

        if kind in ("start", "void") and tag in DROP_TREE:
            if kind == "start":
                drop_depth = 1
                drop_tag = tag
            continue

        if kind == "text":
            out.append(html.escape(payload, quote=False))
            continue

        if kind == "void":
            if tag in ALLOWED:
                out.append(f"<{tag}{attr_str(tag, payload)}>")
            continue

        if kind == "start":
            if tag in ALLOWED:
                out.append(f"<{tag}{attr_str(tag, payload)}>")
                stack.append(tag)
            else:
                # 出力しないタグは、閉じるときに無視できるよう覚えておく
                skipped.append(tag)
            continue

        # kind == "end"
        if skipped and skipped[-1] == tag:
            skipped.pop()
            continue
        if tag in stack:
            # 対応する開始タグまで、間に開いたままのタグをすべて閉じる
            while stack:
                top = stack.pop()
                out.append(f"</{top}>")
                if top == tag:
                    break
        # 対応する開始タグがない終了タグは捨てる

    while stack:
        out.append(f"</{stack.pop()}>")

    return "".join(out)


def attr_str(tag, d):
    if not d:
        return ""
    parts = []
    for k, v in d.items():
        if k not in KEEP_ATTRS:
            continue
        if v is None:
            continue
        # Google Sites の画像プロキシURLはそのまま使えるので保持する
        parts.append(f' {k}="{html.escape(v, quote=True)}"')
    return "".join(parts)


def unwrap_bare_divs(s):
    """属性のない <div>...</div> を、対応関係を保ったまま取り除く。

    Google Sites は入れ物としての div を何重にも重ねる。中身を残したまま
    この入れ物だけを外すことで、あとから手で編集しやすいHTMLになる。
    """
    tokens = re.split(r"(<div\b[^>]*>|</div>)", s)
    out = []
    stack = []  # True なら「この div は出力していない」
    for tok in tokens:
        if tok.startswith("<div"):
            bare = tok == "<div>"
            stack.append(bare)
            if not bare:
                out.append(tok)
        elif tok == "</div>":
            if stack:
                bare = stack.pop()
                if not bare:
                    out.append(tok)
            # 対応する開始タグがない終了タグは捨てる
        else:
            out.append(tok)
    return "".join(out)


def tidy(fragment):
    """空タグや無意味な入れ子を畳んで読みやすくする。"""
    s = fragment
    # 見出しリンクコピー用の残骸を除去
    s = re.sub(r'<a[^>]*href="#h\.[^"]*"[^>]*></a>', "", s)
    # 中身のない span / div を繰り返し除去
    for _ in range(12):
        before = s
        s = re.sub(r"<(span|div)>\s*</\1>", "", s)
        s = re.sub(r"<(span|div)>(\s*)</\1>", r"\2", s)
        if s == before:
            break
    # span で囲んだだけのものは中身に置き換える（入れ子の内側から）
    for _ in range(12):
        before = s
        s = re.sub(r"<span>([^<]*)</span>", r"\1", s)
        if s == before:
            break
    # 属性のない div は入れ物としての意味がないので、開始と終了を対にして外す。
    # 開始だけ、終了だけを個別に消すとタグの対応が崩れるため、対で扱う。
    s = unwrap_bare_divs(s)
    # 空の段落・見出しを落とす
    s = re.sub(r"<(p|h[1-6])>\s*</\1>", "", s)
    # 余分な空白を整理
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    # ブロック要素の前で改行して読みやすく
    for t in ["p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li",
              "table", "tr", "blockquote", "div", "iframe", "img", "hr"]:
        s = s.replace(f"<{t}>", f"\n<{t}>").replace(f"<{t} ", f"\n<{t} ")
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def page_title(raw_html):
    m = re.search(r"<title>(.*?)</title>", raw_html, re.S)
    if m:
        return html.unescape(m.group(1)).strip()
    return ""


def filename_to_path(fn):
    """home__kotodama.html -> /home/kotodama"""
    stem = fn[:-5]
    if stem == "index":
        return "/"
    return "/" + stem.replace("__", "/")


def main():
    os.makedirs(SITE, exist_ok=True)
    files = sorted(f for f in os.listdir(RAW) if f.endswith(".html"))
    manifest = []

    for fn in files:
        raw_html = open(os.path.join(RAW, fn), encoding="utf-8").read()
        parser = MainExtractor()
        try:
            parser.feed(raw_html)
        except Exception as exc:
            print(f"  解析に失敗: {fn} ({exc})", file=sys.stderr)
            continue

        if not parser.results:
            print(f"  本文が見つからない: {fn}", file=sys.stderr)
            body = ""
        else:
            body = "\n".join(tidy(render(c)) for c in parser.results)

        title = page_title(raw_html)
        path = filename_to_path(fn)
        text_len = len(re.sub(r"<[^>]+>", "", body))
        manifest.append({
            "file": fn,
            "path": path,
            "title": title,
            "html_len": len(body),
            "text_len": text_len,
        })

        out = os.path.join(SITE, fn.replace(".html", ".fragment.html"))
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(body)

        print(f"{path:45s} 本文 {text_len:6d} 文字  「{title}」")

    with open(os.path.join(ROOT, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    total = sum(m["text_len"] for m in manifest)
    print(f"\n{len(manifest)} ページ、本文合計 {total} 文字を抽出した。")


if __name__ == "__main__":
    main()
