#!/usr/bin/env python3
"""
產生 Jekyll 格式的 markdown posts從 DB（給 GitHub Pages 用）。
"""

import sqlite3
import re
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path("articles.db")
POSTS_DIR = Path("_posts")


def generate_posts(limit=10):
    POSTS_DIR.mkdir(exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT url, title, zh_title, published, translation
            FROM articles
            WHERE translation IS NOT NULL AND translation != ''
            ORDER BY published DESC LIMIT ?
        """, (limit,)).fetchall()

    count = 0
    for r in rows:
        url = r["url"]
        m = re.search(r"/posts/(\d{4})/(\d{2})/(\d{2})/", url)
        if not m:
            continue
        year, month, day = m.group(1), m.group(2), m.group(3)
        title = r["zh_title"] or r["title"]
        slug = re.sub(r"[^\w\s\u4e00-\u9fff]", "", title)
        slug = re.sub(r"[\s]+", "-", slug)[:50]
        filename = POSTS_DIR / f"{year}-{month}-{day}-{slug}.md"

        content = r["translation"]
        #簡易分段：把 \n\n 轉成 <p>
        paras = [p.strip() for p in content.split("\n\n") if p.strip()]
        body = "\n".join(f"<p>{p}</p>" for p in paras)

        fm = f"""---
layout: post
title: "{title}"
date: {year}-{month}-{day} 00:00:00 +0800
category: translation
original_url: "{url}"
---

{body}
"""
        filename.write_text(fm, encoding="utf-8")
        count += 1

    logger.info(f"產生 {count} 篇 Jekyll posts")
    return count


if __name__ == "__main__":
    generate_posts()