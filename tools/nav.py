#!/usr/bin/env python3
"""元サイトのナビゲーションを raw/home.html から取り出し、nav.json に保存する。

ナビゲーションは、日本語のプロジェクト一覧・英語版・その他のページという
3つのまとまりでできている。ここでは並び順を元サイトのまま保つ。
"""
import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build():
    raw = open(os.path.join(ROOT, "raw", "home.html"), encoding="utf-8").read()
    seg = re.search(r"<nav[^>]*>.*?</nav>", raw, re.S).group(0)

    items = []
    seen = set()
    for a in re.finditer(r'<a\b[^>]*href="([^"]+)"[^>]*>(.*?)</a>', seg, re.S):
        href = a.group(1)
        label = html.unescape(re.sub(r"<[^>]+>", "", a.group(2))).strip()
        if not label or not href.startswith("/"):
            continue
        key = (href, label)
        if key in seen:
            continue
        seen.add(key)
        items.append({"href": href, "label": label})

    # 先頭の「Kazutaka Kurihara」はサイト名なので、ナビ項目からは外す
    if items and items[0]["label"] == "Kazutaka Kurihara":
        items = items[1:]

    groups = []
    current = None
    for it in items:
        # 「日本語」「English」は section の見出しとして扱う
        if it["label"] in ("日本語", "English"):
            current = {"title": it["label"], "href": it["href"], "children": []}
            groups.append(current)
            continue
        if current is None or not it["href"].startswith(current["href"]):
            current = None
            groups.append({"title": it["label"], "href": it["href"], "children": []})
        else:
            current["children"].append(it)

    out = os.path.join(ROOT, "nav.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(groups, fh, ensure_ascii=False, indent=2)

    total = sum(1 + len(g["children"]) for g in groups)
    print(f"ナビゲーションを {len(groups)} 個のまとまり、計 {total} 項目として保存した。")
    for g in groups:
        print(f"  {g['title']}  ({len(g['children'])} 項目)")


if __name__ == "__main__":
    build()
