#!/usr/bin/env python3
"""本文中の画像をローカルに保存し、Google経由のリダイレクトリンクを本来のURLに戻す。

Google Sites の画像は lh3.googleusercontent.com 上にあり、サイトを移行すると
将来的に参照できなくなる可能性がある。そこで assets/img/ に実体を保存し、
参照先を相対パスに書き換える。
外部リンクは https://www.google.com/url?q=... というリダイレクトを経由しているため、
q= パラメータを取り出して本来のURLに直す。
"""
import hashlib
import os
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
IMGDIR = os.path.join(ROOT, "assets", "img")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

EXT_BY_TYPE = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/svg+xml": ".svg",
}


def unwrap_google_redirect(url):
    """https://www.google.com/url?q=<本来のURL>&... から本来のURLを取り出す。"""
    if not url.startswith("https://www.google.com/url?"):
        return url
    qs = urllib.parse.urlparse(url).query
    params = urllib.parse.parse_qs(qs)
    target = params.get("q", [None])[0]
    return target or url


def download(url, dest_dir):
    """画像を取得して保存し、保存先のファイル名を返す。失敗したらNone。"""
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    # すでに取得済みなら再利用する
    for existing in os.listdir(dest_dir):
        if existing.startswith(key + "."):
            return existing
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
    except Exception as exc:
        print(f"  画像取得に失敗: {url[:80]} ({exc})", file=sys.stderr)
        return None

    ext = EXT_BY_TYPE.get(ctype, "")
    if not ext:
        ext = os.path.splitext(urllib.parse.urlparse(url).path)[1] or ".img"
    name = key + ext
    with open(os.path.join(dest_dir, name), "wb") as fh:
        fh.write(data)
    return name


def main():
    os.makedirs(IMGDIR, exist_ok=True)
    files = sorted(f for f in os.listdir(SITE) if f.endswith(".fragment.html"))

    # まず全ページから画像URLを集める
    all_imgs = set()
    for fn in files:
        s = open(os.path.join(SITE, fn), encoding="utf-8").read()
        all_imgs |= set(re.findall(r'<img[^>]*src="([^"]+)"', s))

    print(f"画像 {len(all_imgs)} 点を取得する。")
    mapping = {}
    for i, url in enumerate(sorted(all_imgs), 1):
        if url.startswith("data:"):
            continue
        name = download(url, IMGDIR)
        if name:
            mapping[url] = "/assets/img/" + name
            print(f"  [{i}/{len(all_imgs)}] {name}")
        time.sleep(0.15)

    # 各ページを書き換える
    for fn in files:
        path = os.path.join(SITE, fn)
        s = open(path, encoding="utf-8").read()

        # 画像の参照先をローカルに
        for url, local in mapping.items():
            s = s.replace(f'src="{url}"', f'src="{local}"')

        # Googleリダイレクトを本来のURLに戻す
        def fix_href(m):
            raw = m.group(1)
            # HTMLエスケープを戻してから処理する
            unescaped = raw.replace("&amp;", "&")
            fixed = unwrap_google_redirect(unescaped)
            return 'href="' + fixed.replace("&", "&amp;") + '"'

        s = re.sub(r'href="(https://www\.google\.com/url\?[^"]+)"', fix_href, s)

        # YouTube埋め込みから、Google Sites 固有の embed_config を落とす
        s = re.sub(r'(<iframe[^>]*src="https://www\.youtube\.com/embed/[\w-]+)\?[^"]*"',
                   r'\1"', s)

        # 画像に遅延読み込みを付ける
        s = s.replace("<img ", '<img loading="lazy" ')

        with open(path, "w", encoding="utf-8") as fh:
            fh.write(s)

    print(f"\n{len(mapping)} 点の画像をローカル化し、{len(files)} ページのリンクを整えた。")


if __name__ == "__main__":
    main()
