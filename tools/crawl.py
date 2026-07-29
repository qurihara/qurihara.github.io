#!/usr/bin/env python3
"""unryu.org（新しいGoogle Sites）の公開ページをすべて取得して raw/ に保存する。

Google Sites は公開ページをサーバ側でHTMLとして返すため、認証なしで取得できる。
ここでは取得のみを行い、解析・変換は extract.py が担当する。
"""
import os
import re
import sys
import time
import urllib.request
import urllib.error
from urllib.parse import urljoin, urlparse

BASE = "https://www.unryu.org"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "raw")


def fetch(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as exc:
            if attempt == retries - 1:
                print(f"  取得失敗: {url} ({exc})", file=sys.stderr)
                return None
            time.sleep(2 * (attempt + 1))
    return None


def path_to_filename(path):
    """/home/kotodama -> home__kotodama.html、/ -> index.html"""
    p = path.strip("/")
    if not p:
        return "index.html"
    return p.replace("/", "__") + ".html"


def internal_links(html_text):
    """同一サイト内のリンクパスを集める。"""
    found = set()
    for href in re.findall(r'href="([^"]+)"', html_text):
        if href.startswith("/") and not href.startswith("//"):
            path = href.split("#")[0].split("?")[0]
            if path:
                found.add(path)
        elif href.startswith(BASE):
            path = urlparse(href).path.split("#")[0]
            if path:
                found.add(path)
    return found


def main():
    os.makedirs(RAW, exist_ok=True)
    queue = ["/"]
    seen = set()
    saved = 0

    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)

        url = urljoin(BASE, path)
        print(f"取得中: {url}")
        html_text = fetch(url)
        if html_text is None:
            continue

        out = os.path.join(RAW, path_to_filename(path))
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html_text)
        saved += 1

        for link in sorted(internal_links(html_text)):
            # 添付ファイルやシステム用のパスは辿らない
            if link.startswith("/system/") or link.startswith("/_/"):
                continue
            if link not in seen:
                queue.append(link)

        time.sleep(0.4)

    print(f"\n完了。{saved} ページを {RAW} に保存した。")


if __name__ == "__main__":
    main()
