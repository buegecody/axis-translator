#!/usr/bin/env python3
"""
Axis Scraper — Sitemap 發現 + Jina 抓取 + SQLite 去重 + 進度Checkpoint
"""

import os
import sqlite3
import hashlib
import time
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path("articles.db")
PROGRESS_FILE = Path("sitemap_progress.txt")
REQUEST_DELAY = 2.5
MAX_ARTICLES_PER_RUN = 30

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AxisTransBot/1.0)"}
JINA_PREFIX = "https://r.jina.ai/"
SITEMAP_INDEX_URL = "https://www.axismag.jp/sitemap.xml"


class AxisScraper:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.progress_file = PROGRESS_FILE
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS articles (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    url         TEXT UNIQUE NOT NULL,
                    url_hash    TEXT UNIQUE NOT NULL,
                    title       TEXT,
                    published   TEXT,
                    category TEXT,
                    content TEXT,
                    zh_title    TEXT,
                    translation TEXT,
                    fetched_at  TEXT NOT NULL,
                    sent        INTEGER DEFAULT 0
                )
            """)
            existing = {row[1] for row in conn.execute("PRAGMA table_info(articles)")}
            for col, definition in [
                ("zh_title",     "TEXT"),
                ("translation",  "TEXT"),
                ("category",     "TEXT"),
            ]:
                if col not in existing:
                    conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {definition}")
            conn.commit()

    def _url_hash(self, url):
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _is_seen(self, url):
        h = self._url_hash(url)
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(
                "SELECT 1 FROM articles WHERE url_hash = ?", (h,)
            ).fetchone() is not None

    def _get_progress(self):
        if self.progress_file.exists():
            parts = self.progress_file.read_text().strip().split(",")
            return int(parts[0]), int(parts[1])
        return 0, 0

    def _save_progress(self, sitemap_idx, url_idx):
        self.progress_file.write_text(f"{sitemap_idx},{url_idx}")

    def _fetch_all_sitemap_urls(self):
        """抓 sitemap-index.xml，取得所有 post_list-sitemap*.xml URL"""
        try:
            import requests
            resp = requests.get(SITEMAP_INDEX_URL, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            logger.error("Sitemap-index 讀取失敗：" + str(e))
            return []

        urls = []
        try:
            root = ET.fromstring(resp.content)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for loc in root.findall(".//sm:loc", ns):
                url = loc.text.strip()
                if "post_list-sitemap" in url:
                    urls.append(url)
        except Exception as e:
            logger.error("Sitemap-index 解析失敗：" + str(e))
            return []

        # 按編號由新到舊
        urls.sort(
            key=lambda u: int(re.search(r"sitemap(\d+)", u).group(1))
            if re.search(r"sitemap(\d+)", u) else 0,
            reverse=True
        )
        logger.info(f"發現 {len(urls)} 個 sitemap")
        return urls

    def _fetch_sitemap_urls(self, sitemap_url):
        """抓單個 sitemap，回傳 [(url, published_date)]"""
        try:
            import requests
            resp = requests.get(sitemap_url, headers=HEADERS, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Sitemap 讀取失敗：{sitemap_url} — {e}")
            return []

        urls = []
        try:
            root = ET.fromstring(resp.content)
            ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
            for url_el in root.findall(".//sm:url", ns):
                loc = url_el.find("sm:loc", ns)
                lastmod = url_el.find("sm:lastmod", ns)
                if loc is None:
                    continue
                url = loc.text.strip()
                if not re.search(r"/posts/\d{4}/\d{2}/\d+\.html", url):
                    continue
                published = ""
                if lastmod is not None and lastmod.text:
                    raw = lastmod.text.strip()
                    try:
                        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                        tw_tz = timezone(timedelta(hours=8))
                        published = dt.astimezone(tw_tz).strftime("%Y-%m-%d %H:%M")
                    except Exception:
                        published = raw[:10]
                urls.append((url, published))
        except Exception as e:
            logger.error(f"Sitemap 解析失敗：{sitemap_url} — {e}")

        urls.sort(key=lambda x: x[1], reverse=True)
        return urls

    def _fetch_article(self, url, published=""):
        """用 Jina.ai 抓乾淨文字內容"""
        jina_url = JINA_PREFIX + url
        try:
            import requests
            resp = requests.get(jina_url, headers=HEADERS, timeout=30)
            if resp.status_code != 200:
                logger.info(f"  Jina 跳過（{resp.status_code}）：{url[:60]}")
                return None
        except Exception as e:
            logger.debug(f"  Jina 抓取失敗：{e}")
            return None

        text = resp.text.strip()
        if len(text) < 100:
            logger.info(f"  內容太短：{url[:60]}")
            return None

        lines = text.split("\n")
        title = ""
        content_lines = []
        article_started = False
        date_pattern = re.compile(r"\d{4}\.\d{2}\.\d{2}")

        SKIP_KEYWORDS = [
            "FOLLOW US", "Facebook", "Twitter", "Instagram", "YouTube", "LINE",
            "Spotify", "プライバシー", "お問い合わせ", "運営会社", "広告掲載",
            "採用情報", "関連する記事", "### [NEWS", "#### [", "AXIS WEB",
            "WANTED", "DISPLAY", "CLASSIFIEDS",
        ]

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("# ") and not title:
                candidate = stripped.lstrip("#").strip()
                if "AXIS WEB" not in candidate and "axismag" not in candidate.lower():
                    title = candidate
                continue

            if not article_started and date_pattern.search(stripped):
                article_started = True
                continue

            if article_started:
                if any(kw in stripped for kw in SKIP_KEYWORDS):
                    continue
                if stripped.startswith("*   [") or stripped.startswith("- ["):
                    continue
                content_lines.append(stripped)

        if not title or len(title) < 5:
            logger.info(f"  無標題跳過：{url[:60]}")
            return None

        content = "\n\n".join(content_lines)
        if len(content) < 50:
            logger.info(f"  內文太短：{title[:30]}")
            return None

        if not published:
            m = re.search(r"/posts/(\d{4})/(\d{2})/", url)
            published = f"{m.group(1)}-{m.group(2)}" if m else ""

        logger.info(f"  ✓ {title[:45]}（{len(content)} 字）")
        return {
            "url":       url,
            "title":     title,
            "published": published,
            "content":   content[:4000],
        }

    def _save_article(self, article):
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO articles
                        (url, url_hash, title, published, content, fetched_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    article["url"],
                    self._url_hash(article["url"]),
                    article.get("title", ""),
                    article.get("published", ""),
                    article.get("content", ""),
                    datetime.utcnow().isoformat(),
                ))
                conn.commit()
            except sqlite3.IntegrityError:
                pass

    def run(self):
        """抓新文章，回傳新文章列表"""
        sitemap_idx, url_idx = self._get_progress()
        logger.info(f"進度Checkpoint：sitemap {sitemap_idx}, url {url_idx}")

        all_sitemaps = self._fetch_all_sitemap_urls()
        if not all_sitemaps:
            logger.error("無法取得 sitemap 清單")
            return []

        new_articles = []

        while len(new_articles) < MAX_ARTICLES_PER_RUN:
            if sitemap_idx >= len(all_sitemaps):
                logger.info("所有 sitemap 已讀完，重置進度")
                self._save_progress(0, 0)
                break

            sitemap_url = all_sitemaps[sitemap_idx]
            logger.info(f"讀取 sitemap：{sitemap_url}")
            urls = self._fetch_sitemap_urls(sitemap_url)

            if not urls:
                sitemap_idx += 1
                url_idx = 0
                self._save_progress(sitemap_idx, url_idx)
                continue

            logger.info(f"  共 {len(urls)} 篇，從第 {url_idx} 筆繼續")

            while url_idx < len(urls):
                if len(new_articles) >= MAX_ARTICLES_PER_RUN:
                    break

                url, published = urls[url_idx]
                url_idx += 1

                if self._is_seen(url):
                    continue

                time.sleep(REQUEST_DELAY)
                article = self._fetch_article(url, published)
                if article:
                    self._save_article(article)
                    new_articles.append(article)

            if url_idx >= len(urls):
                sitemap_idx += 1
                url_idx = 0

            self._save_progress(sitemap_idx, url_idx)

        logger.info(f"共新增 {len(new_articles)} 篇文章")
        return new_articles

    def get_unsent(self, limit=1):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM articles
                WHERE sent = 0 AND translation IS NOT NULL AND translation != ''
                ORDER BY published DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def mark_sent(self, ids):
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                "UPDATE articles SET sent = 1 WHERE id = ?",
                [(i,) for i in ids]
            )
            conn.commit()

    def get_stats(self):
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
            pending = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE sent = 0 AND translation IS NOT NULL AND translation != ''"
            ).fetchone()[0]
            no_trans = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE translation IS NULL OR translation = ''"
            ).fetchone()[0]
            sent    = conn.execute("SELECT COUNT(*) FROM articles WHERE sent = 1").fetchone()[0]
        return total, pending, no_trans, sent