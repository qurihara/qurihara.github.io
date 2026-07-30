#!/usr/bin/env python3
"""研究室ページの各研究に、ProtoPediaに載っている紹介動画を貼る。

研究室ページ（site/lab.fragment.html）には、研究ごとにProtoPediaへのリンクがある。
そのProtoPediaのページには、たいてい紹介動画（YouTube）が埋め込まれている。
そこで、リンク先から動画のIDを取り出し、研究室ページにも同じ動画を貼る。

2025年度の書き方にならい、見出しと本文を含むまとまりの直後に、
動画だけを入れたまとまりを置く。

  <div class="blk">
  <iframe src="https://www.youtube.com/embed/動画のID"></iframe>
  </div>

すでに動画が貼られている研究は、そのままにする。
"""
import json
import os
import re
import sys
import time
import urllib.request

PAGE = "site/lab.fragment.html"
CACHE = "tools/protopedia_media.json"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch_media(url):
    """ProtoPediaのページから、埋め込まれている動画のIDと作品名を取り出す。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as res:
        html = res.read().decode("utf-8", "replace")
    video = None
    for pat in (r"youtube\.com/embed/([\w-]+)",
                r"youtu\.be/([\w-]+)",
                r"youtube\.com/watch\?v=([\w-]+)"):
        m = re.search(pat, html)
        if m:
            video = m.group(1)
            break
    name = re.search(r"<title>(.*?)\s*\|\s*ProtoPedia</title>", html, re.S)
    return {"video": video,
            "name": re.sub(r"\s+", " ", name.group(1)).strip() if name else None}


def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)


def split_entries(html):
    """<h3> で始まる研究の単位に切り分け、各単位の範囲を返す。"""
    heads = [m for m in re.finditer(r"<h3>(?:<a[^>]*></a>)?(.*?)</h3>", html, re.S)]
    spans = []
    for i, m in enumerate(heads):
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(html)
        spans.append({"title": title, "start": m.start(), "end": end})
    return spans


def main():
    dry = "--dry-run" in sys.argv
    html = open(PAGE, encoding="utf-8").read()
    cache = load_cache()

    spans = split_entries(html)
    plans = []
    for sp in spans:
        body = html[sp["start"]:sp["end"]]
        if "youtube.com/embed" in body:
            continue  # すでに動画がある
        m = re.search(r'href="(https://protopedia\.net/prototype/\d+)"', body)
        if not m:
            continue
        url = m.group(1)
        if url not in cache:
            try:
                cache[url] = fetch_media(url)
            except Exception as exc:
                cache[url] = {"video": None, "name": None, "error": str(exc)[:60]}
            time.sleep(0.4)
        video = cache[url].get("video")
        if not video:
            print(f"  動画なし  {sp['title'][:44]}")
            continue
        plans.append({**sp, "video": video, "url": url,
                      "name": cache[url].get("name")})
    save_cache(cache)

    print(f"\n動画を貼る対象: {len(plans)}件")
    for p in plans:
        print(f"  {p['video']}  {p['title'][:46]}")
    if dry:
        print("\n--dry-run のため書き込まない")
        return

    # 後ろから差し込む。前から入れると位置がずれるためである。
    for p in sorted(plans, key=lambda x: x["start"], reverse=True):
        block = (f'<div class="blk">\n'
                 f'<iframe src="https://www.youtube.com/embed/{p["video"]}"></iframe>\n'
                 f'</div>\n')
        # その研究のまとまりの末尾、次の見出しの直前に置く
        pos = p["end"]
        html = html[:pos] + block + html[pos:]

    with open(PAGE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n{len(plans)}件の動画を貼った。")


if __name__ == "__main__":
    main()
