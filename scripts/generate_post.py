#!/usr/bin/env python3
"""Generate Jekyll post from translated content."""

import sys
import json
import re
from datetime import datetime

if __name__ == "__main__":
    data = sys.stdin.read()
    idx = data.find("---JSON_OUTPUT---")
    if idx == -1:
        print("ERROR: No JSON_OUTPUT marker found", file=sys.stderr)
        sys.exit(1)
    json_str = data[idx + len("---JSON_OUTPUT---"):].strip()
    article = json.loads(json_str)

    url = article["url"]
    # Extract date from URL: https://www.axismag.jp/posts/YYYY/MM/DD/ID.html
    m = re.search(r"/posts/(\d{4})/(\d{2})/(\d{2})/", url)
    if m:
        year, month, day = m.group(1), m.group(2), m.group(3)
    else:
        d = datetime.now()
        year, month, day = d.strftime("%Y"), d.strftime("%m"), d.strftime("%d")

    title_slug = re.sub(r"[^\w\s\u4e00-\u9fff]", "", article["title"])
    title_slug = re.sub(r"[\s]+", "-", title_slug)
    # Build filename
    filename = f"_posts/{year}-{month}-{day}-{title_slug[:40]}.md"

    # Category from URL or default
    category = "翻譯"

    # Format translated content as paragraphs
    paragraphs = [p.strip() for p in article["translated"].split("\n\n") if p.strip()]
    content_html = "\n".join(f"<p>{p}</p>" for p in paragraphs)

    front_matter = f"""---
layout: post
title: "{article['title']}"
date: {year}-{month}-{day} 00:00:00 +0800
category: {category}
original_url: "{url}"
---

{content_html}
"""

    with open(filename, "w", encoding="utf-8") as f:
        f.write(front_matter)
    print(f"Written: {filename}", file=sys.stderr)

    # Forward JSON for the next pipe stage
    print("---JSON_OUTPUT---")
    print(json_str)
