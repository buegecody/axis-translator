#!/usr/bin/env python3
"""
Axis Translator — 從 DB 讀取未翻譯文章，翻譯標題+內文後寫回 DB。
"""

import os
import sys
import json
import time
import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "articles.db"
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
API_BASE = "https://api.minimax.chat/v1"
MODEL = "MiniMax-Text-01"
CHUNK_SIZE = 1400
MAX_RETRIES = 3


def translate_chunk(chunk: str) -> str | None:
    """翻譯單個文字區塊，重試 3 次。失敗回傳 None。"""
    prompt = f"""你是一個專業日文翻譯。請將以下日文完整翻譯成繁體中文（台灣用語），只輸出翻譯結果，不要有任何其他解釋或標記。禁止輸出簡體中文。

{chunk}"""
    payload = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2000
    }).encode()

    import subprocess
    payload_file = "/tmp/trans_payload.json"
    with open(payload_file, "wb") as f:
        f.write(payload)

    for attempt in range(MAX_RETRIES):
        result = subprocess.run(
            ["curl", "-s", "-X", "POST",
             f"{API_BASE}/chat/completions",
             "-H", "Content-Type: application/json",
             "-H", f"Authorization: Bearer {MINIMAX_API_KEY}",
             "-d", f"@{payload_file}"],
            capture_output=True, text=True, timeout=60
        )
        try:
            data = json.loads(result.stdout)
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.warning(f"  Chunk嘗試 {attempt+1} 失敗：{e}")
            time.sleep(5)
    return None


def translate_text(text: str) -> str:
    """分塊翻譯長文，合併結果。"""
    if not text:
        return ""

    chunks, current = [], ""
    for para in text.split("。"):
        para += "。"
        if len(current) + len(para) <= CHUNK_SIZE:
            current += para
        else:
            if current:
                chunks.append(current.strip())
            current = para
    if current.strip():
        chunks.append(current.strip())

    translated = []
    for i, chunk in enumerate(chunks):
        logger.info(f"  翻譯 chunk {i+1}/{len(chunks)}（{len(chunk)} 字）...")
        result = translate_chunk(chunk)
        if result is None:
            logger.error(f"  Chunk {i+1} 全部失敗，跳過")
            continue
        translated.append(result)

    return "\n\n".join(translated)


def translate_title(title: str) -> str:
    """翻譯標題。"""
    if not title:
        return title
    result = translate_chunk(title)
    return result if result else title


def _clean_ai_blather(text: str) -> str:
    """移除 AI 自言自語的干擾句。"""
    lines = text.split("\n")
    skip_prefixes = [
        "從文章", "翻譯成繁體中文", "以下是翻譯", "以下是摘要", "以下是評論",
        "我需要", "我注意到", "現在我", "讓我來", "接下來我將", "根據文章",
        "根據以上", "以下為", "犀利開篇", "引用案例", "點出盲點", "金句結尾",
        "直接輸出", "要點一", "要點二", "要點三",
        "核心主題", "延伸思考",
        "The user", "Let me", "I need", "I will", "I'll", "I should",
        "Here is", "Here's", "Let's", "This is", "Please note",
    ]
    cleaned = [l for l in lines if not any(l.strip().startswith(p) for p in skip_prefixes)]
    return "\n".join(cleaned).strip()


def process_pending(max_articles=20):
    """抓 DB 中未翻譯的文章，翻譯後寫回。回傳處理的篇數。"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT id, url, title, content
            FROM articles
            WHERE (translation IS NULL OR translation = '')
              AND content IS NOT NULL AND content != ''
            ORDER BY published DESC
            LIMIT ?
        """, (max_articles,)).fetchall()

    if not rows:
        logger.info("沒有待翻譯文章")
        return 0

    articles = [dict(r) for r in rows]
    done = 0

    for art in articles:
        logger.info(f"翻譯：{art['title'][:50]}")

        zh_title = translate_title(art["title"])
        zh_title = _clean_ai_blather(zh_title)
        if not zh_title or zh_title == art["title"]:
            zh_title = art["title"]

        zh_content = translate_text(art["content"][:3500])
        zh_content = _clean_ai_blather(zh_content)

        if len(zh_content) < 50:
            logger.warning(f"  翻譯結果太短（{len(zh_content)} 字），跳過")
            continue

        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                UPDATE articles
                SET zh_title = ?, translation = ?
                WHERE id = ?
            """, (zh_title, zh_content, art["id"]))
            conn.commit()

        done += 1
        logger.info(f"  ✓ 完成（標題 {len(zh_title)} 字，內文 {len(zh_content)} 字）")
        time.sleep(1.5)

    return done


if __name__ == "__main__":
    max_articles = int(os.environ.get("MAX_TRANSLATE", 20))
    done = process_pending(max_articles)
    logger.info(f"翻譯完成，共 {done} 篇")
    sys.exit(0)