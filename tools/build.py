#!/usr/bin/env python3
"""unryu.org を取得し、本文を抜き出し、画像を保存して、素のHTMLサイトを組み立てる。

Google Sites の画像URL（lh3.googleusercontent.com/sitesv/...）に含まれるトークンは
リクエストごとに変わり、しばらくすると失効する。そのためページの取得と画像の取得は
1ページずつ続けて行う必要がある。この点が、取得と変換を別々の工程に分けられない理由である。

画像は内容のハッシュで名前を付けるため、同じ画像が複数ページで使われていても
実体はひとつだけ保存される。
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import MainExtractor, render, tidy, page_title, filename_to_path  # noqa: E402

BASE = "https://www.unryu.org"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
IMGDIR = os.path.join(ROOT, "assets", "img")

EXT_BY_TYPE = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/svg+xml": ".svg", "image/x-icon": ".ico",
}


def http_get(url, binary=False, retries=3, referer=BASE + "/"):
    headers = {
        "User-Agent": UA,
        "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        "Referer": referer,
    }
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
                ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
                return (data, ctype) if binary else (data.decode("utf-8", "replace"), ctype)
        except Exception as exc:
            if attempt == retries - 1:
                print(f"    取得失敗: {url[:90]} ({exc})", file=sys.stderr)
                return (None, None)
            time.sleep(1.5 * (attempt + 1))
    return (None, None)


def save_image(url, index_by_hash):
    """画像を取得して assets/img に保存し、サイト内での参照パスを返す。"""
    data, ctype = http_get(url, binary=True)
    if data is None or len(data) < 64:
        return None
    digest = hashlib.sha1(data).hexdigest()[:16]
    if digest in index_by_hash:
        return index_by_hash[digest]

    ext = EXT_BY_TYPE.get(ctype, "")
    if not ext:
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".jpg"
    name = digest + ext
    with open(os.path.join(IMGDIR, name), "wb") as fh:
        fh.write(data)
    ref = "assets/img/" + name
    index_by_hash[digest] = ref
    return ref


def unwrap_google_redirect(url):
    """http(s)://www.google.com/url?q=<本来のURL>&... を本来のURLに戻す。"""
    if not re.match(r"https?://www\.google\.com/url\?", url):
        return url
    params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return params.get("q", [url])[0]


def clean_links(fragment):
    """Google経由のリダイレクトを外し、YouTube埋め込みの余分な引数を落とす。"""
    def fix(m):
        raw = m.group(1).replace("&amp;", "&")
        return 'href="' + html.escape(unwrap_google_redirect(raw), quote=True) + '"'

    s = re.sub(r'href="(https?://www\.google\.com/url\?[^"]+)"', fix, fragment)
    s = re.sub(r'(<iframe[^>]*src="https://www\.youtube\.com/embed/[\w-]+)\?[^"]*"',
               r'\1"', s)
    # //example.com という書き方は外部サイトへのリンクなので、https を補う
    s = re.sub(r'href="//([^"]+)"', r'href="https://\1"', s)
    # 内部リンクは末尾の .html を持たないパスのままにしておく（後段で解決する）
    return s


def discover_paths():
    """トップページから辿って、サイト内の全ページのパスを集める。"""
    queue = ["/"]
    seen = []
    visited = set()
    while queue:
        path = queue.pop(0)
        if path in visited:
            continue
        visited.add(path)
        text, _ = http_get(urllib.parse.urljoin(BASE, path))
        if text is None:
            continue
        seen.append(path)
        for href in re.findall(r'href="(/[^"#?]*)"', text):
            if href.startswith("//") or href.startswith("/system/") or href.startswith("/_/"):
                continue
            if href not in visited:
                queue.append(href)
        time.sleep(0.3)
    return seen


def main():
    os.makedirs(SITE, exist_ok=True)
    os.makedirs(IMGDIR, exist_ok=True)

    print("ページ一覧を調べている。")
    paths = discover_paths()
    print(f"{len(paths)} ページを見つけた。\n")

    index_by_hash = {}
    # すでに保存済みの画像を把握しておく（再実行時に取り直さないため）
    for name in os.listdir(IMGDIR):
        index_by_hash.setdefault(os.path.splitext(name)[0], "assets/img/" + name)

    manifest = []
    for n, path in enumerate(paths, 1):
        url = urllib.parse.urljoin(BASE, path)
        raw, _ = http_get(url)
        if raw is None:
            continue

        parser = MainExtractor()
        try:
            parser.feed(raw)
        except Exception as exc:
            print(f"  解析に失敗: {path} ({exc})", file=sys.stderr)
            continue

        body = "\n".join(tidy(render(c)) for c in parser.results)
        body = clean_links(body)

        # このページの画像を、URLが失効する前にすぐ保存する
        img_urls = re.findall(r'<img[^>]*src="(https?://[^"]+)"', body)
        for iu in dict.fromkeys(img_urls):
            ref = save_image(iu, index_by_hash)
            if ref:
                body = body.replace(f'src="{iu}"', f'src="/{ref}"')

        body = body.replace("<img ", '<img loading="lazy" ')

        title = page_title(raw)
        text_len = len(re.sub(r"<[^>]+>", "", body))
        fn = ("index" if path == "/" else path.strip("/").replace("/", "__")) + ".fragment.html"
        with open(os.path.join(SITE, fn), "w", encoding="utf-8") as fh:
            fh.write(body)

        manifest.append({
            "path": path, "title": title, "fragment": fn,
            "text_len": text_len, "images": len(set(img_urls)),
        })
        print(f"[{n:2d}/{len(paths)}] {path:42s} 本文{text_len:6d}字 画像{len(set(img_urls)):3d}")
        time.sleep(0.3)

    with open(os.path.join(ROOT, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    total_text = sum(m["text_len"] for m in manifest)
    print(f"\n{len(manifest)} ページ、本文合計 {total_text} 字。")
    print(f"画像 {len(os.listdir(IMGDIR))} 点を {IMGDIR} に保存した。")


if __name__ == "__main__":
    main()
