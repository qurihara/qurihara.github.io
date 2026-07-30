#!/usr/bin/env python3
"""研究室ページの各研究に、ProtoPediaに載っている紹介動画を貼る。

研究室ページ（site/lab.fragment.html）には、研究ごとにProtoPediaへのリンクがある。
そのProtoPediaのページには、たいてい紹介動画（YouTube）が埋め込まれている。
そこで、リンク先から動画のIDを取り出し、研究室ページにも同じ動画を貼る。

貼る位置は、ProtoPediaへのリンクがある箇条書きの項目の直後である。

  <li><p><a href="https://protopedia.net/prototype/1234">protopediaで詳しく見る</a></p></li>
  <li><p><iframe src="https://www.youtube.com/embed/動画のID"></iframe></p></li>

研究の見出しの直後ではなく、リンクの隣に置く理由は2つある。
ひとつは、研究と動画の対応が確実になること。見出しを目印にすると、
どこまでが1つの研究かの判定を誤り、隣の研究の動画を貼ってしまう。
もうひとつは、箇条書きの中に入れることで、リストの入れ子を壊さないことである。

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


def which_entry(html, pos):
    """その位置がどの研究に属するかを、直前の見出しから求める。"""
    heads = [m for m in re.finditer(r"<h3>(?:<a[^>]*></a>)?(.*?)</h3>", html, re.S)
             if m.start() < pos]
    if not heads:
        return "(見出しなし)"
    return re.sub(r"<[^>]+>", "", heads[-1].group(1)).strip()


def main():
    dry = "--dry-run" in sys.argv
    html = open(PAGE, encoding="utf-8").read()
    cache = load_cache()

    # ProtoPediaへのリンクを含む <li> ... </li> を探す
    pattern = re.compile(
        r'<li>\s*<p><a href="(https://protopedia\.net/prototype/\d+)"[^>]*>'
        r'[^<]*</a></p></li>', re.S)

    plans = []
    for m in pattern.finditer(html):
        url = m.group(1)
        title = which_entry(html, m.start())
        # その研究にすでに動画があるかを、見出しから次の見出しまでの範囲で見る
        nxt = re.search(r"<h3>", html[m.end():])
        tail = html[m.end():m.end() + (nxt.start() if nxt else 400)]
        prev_head = [x for x in re.finditer(r"<h3>", html) if x.start() < m.start()]
        head_pos = prev_head[-1].start() if prev_head else 0
        scope = html[head_pos:m.end() + (nxt.start() if nxt else 400)]
        if "youtube.com/embed" in scope:
            continue

        if url not in cache:
            try:
                cache[url] = fetch_media(url)
            except Exception as exc:
                cache[url] = {"video": None, "name": None, "error": str(exc)[:60]}
            time.sleep(0.4)
        video = cache[url].get("video")
        if not video:
            print(f"  動画なし  {title[:44]}")
            continue
        plans.append({"pos": m.end(), "video": video, "title": title,
                      "url": url, "name": cache[url].get("name")})

    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)

    print(f"\n動画を貼る対象: {len(plans)}件")
    for p in plans:
        print(f"  {p['video']}  {p['title'][:46]}")
        print(f"      （ProtoPediaの作品名「{p['name']}」）")
    if dry:
        print("\n--dry-run のため書き込まない")
        return

    # 後ろから差し込む。前から入れると位置がずれるためである。
    for p in sorted(plans, key=lambda x: x["pos"], reverse=True):
        item = (f'\n<li>\n<p><iframe src="https://www.youtube.com/embed/'
                f'{p["video"]}"></iframe></p></li>')
        html = html[:p["pos"]] + item + html[p["pos"]:]

    with open(PAGE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n{len(plans)}件の動画を貼った。")


if __name__ == "__main__":
    main()
