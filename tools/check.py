#!/usr/bin/env python3
"""生成した docs/ を検証する。

確認する内容は次の3つ。
  1. サイト内リンクの飛び先が実在するか。
  2. 参照している画像ファイルが実在するか。
  3. 元サイトの本文の分量と比べて、極端に減っているページがないか。
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")


def page_files():
    for dirpath, _dirnames, filenames in os.walk(DOCS):
        for fn in filenames:
            if fn == "index.html":
                yield os.path.join(dirpath, fn)


def url_path_of(page_file):
    rel = os.path.relpath(os.path.dirname(page_file), DOCS)
    return "/" if rel == "." else "/" + rel.replace(os.sep, "/")


# 同じドメインで配信されるが、この仕組みが作るものではないページ。
# qurihara.github.io の配下にあるプロジェクトサイトは、
# GitHub Pages のはたらきで unryu.org/<名前>/ としても配信される。
# docs/ には無いので、飛び先が無いように見えるが、実際には開ける。
PROJECT_SITES = ("/chordika/", "/ai-fue/")


def exists_as_page(path):
    # 別リポジトリのプロジェクトサイトは、この仕組みの管理外なので確かめない
    if any(path == p or path.startswith(p) for p in PROJECT_SITES):
        return True
    return _exists_as_page(path)


def _exists_as_page(path):
    if path == "/":
        return os.path.exists(os.path.join(DOCS, "index.html"))
    # ページとして存在するか
    if os.path.exists(os.path.join(DOCS, path.strip("/"), "index.html")):
        return True
    # 論文PDFのように、ページではなくファイルとして置いてあるものも飛び先として正しい
    return os.path.isfile(os.path.join(DOCS, path.strip("/")))


def main():
    pages = sorted(page_files())
    print(f"検証するページ数: {len(pages)}\n")

    broken_links = []
    broken_images = []
    link_count = 0
    image_count = 0

    for pf in pages:
        here = url_path_of(pf)
        s = open(pf, encoding="utf-8").read()
        body = s.split('<main id="main"', 1)[-1]

        for href in re.findall(r'href="(/[^"#?]*)"', body):
            # //example.com は外部サイトなので対象外
            if href.startswith("//") or href.startswith("/assets/"):
                continue
            link_count += 1
            if not exists_as_page(href):
                broken_links.append((here, href))

        for src in re.findall(r'src="(/assets/[^"]+)"', s):
            image_count += 1
            if not os.path.exists(os.path.join(DOCS, src.lstrip("/"))):
                broken_images.append((here, src))

    print(f"サイト内リンク {link_count} 件を確認した。")
    if broken_links:
        print(f"  飛び先のないリンクが {len(broken_links)} 件ある。")
        for here, href in sorted(set(broken_links))[:20]:
            print(f"    {here} → {href}")
    else:
        print("  飛び先のないリンクはなかった。")

    print(f"\n画像参照 {image_count} 件を確認した。")
    if broken_images:
        print(f"  実体のない画像が {len(broken_images)} 件ある。")
        for here, src in sorted(set(broken_images))[:20]:
            print(f"    {here} → {src}")
    else:
        print("  実体のない画像はなかった。")

    # 本文量の比較
    manifest = json.load(open(os.path.join(ROOT, "manifest.json"), encoding="utf-8"))
    thin = [m for m in manifest if m["text_len"] < 60]
    print(f"\n本文が極端に少ないページ: {len(thin)} 件")
    for m in thin:
        print(f"    {m['path']}  {m['text_len']}字")

    total = sum(m["text_len"] for m in manifest)
    print(f"\n本文合計 {total} 字、画像 {len(os.listdir(os.path.join(DOCS, 'assets', 'img')))} 点。")

    return 1 if (broken_links or broken_images) else 0


if __name__ == "__main__":
    sys.exit(main())
