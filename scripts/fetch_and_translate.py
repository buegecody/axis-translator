#!/usr/bin/env python3
"""Fetch and translate a single Axis article."""

import sys
import re
import json
import subprocess
from datetime import datetime

MINIMAX_API_KEY = "sk-cp-eu-VuCweXmtbaGuMVG00ayZZp6sh-vYIvRRG5HyzS6P99sfJNR7rBe1XeVRLrHGlVUL2Sc2tbDwbeIpKZheTFgbT6EbOVOlapTwCyl7R9dNLiIKlPF5v0aY"
AXIS_BASE = "https://www.axismag.jp"


def fetch(url: str) -> str:
    result = subprocess.run(
        ["curl", "-sL", "--max-time", "20", "-H", "User-Agent: Mozilla/5.0", url],
        capture_output=True, text=True, timeout=25
    )
    if result.returncode != 0:
        print(f"ERROR fetching {url}: curl returned {result.returncode}", file=sys.stderr)
        sys.exit(1)
    return result.stdout


def extract_title(html: str) -> str:
    # Try specific post_title class first
    m = re.search(r'class="d_title"[^>]*>(.*?)</h1>', html, re.DOTALL)
    if m:
        title = re.sub(r'<br\s*/?>', ' ', m.group(1))
        title = re.sub(r'<[^>]+>', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        if title:
            return title
    # Fallback: any h1
    h1s = re.findall(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    for h in h1s:
        title = re.sub(r'<br\s*/?>', ' ', h)
        title = re.sub(r'<[^>]+>', '', title)
        title = re.sub(r'\s+', ' ', title).strip()
        if title:
            return title
    return ""


def extract_content(html: str) -> str:
    m = re.search(r'<section class="post_content"(.*?)</section>', html, re.DOTALL)
    if not m:
        return ""
    c = m.group(1)
    c = re.sub(r"<script[^>]*>.*?</script>", "", c, flags=re.DOTALL)
    c = re.sub(r"<style[^>]*>.*?</style>", "", c, flags=re.DOTALL)
    c = re.sub(r"<img[^>]*>", "", c)
    c = re.sub(r"<figure[^>]*>.*?</figure>", "", c, flags=re.DOTALL)
    c = re.sub(r"<figcaption[^>]*>.*?</figcaption>", "", c, flags=re.DOTALL)
    c = re.sub(r"<a[^>]*>", "", c)
    c = re.sub(r"</a>", "", c)
    c = re.sub(r"<[^>]+>", "", c)
    c = re.sub(r"\s+", " ", c).strip()
    return c


def get_latest_article_url() -> str:
    html = fetch(AXIS_BASE + "/")
    urls = re.findall(r'href="(https://www\.axismag\.jp/posts/\d+/\d+/\d+\.html)"', html)
    if not urls:
        print("ERROR: No article URLs found on homepage", file=sys.stderr)
        sys.exit(1)
    # Deduplicate and sort by URL date descending
    unique = list(dict.fromkeys(urls))
    unique.sort(key=lambda u: re.search(r"/posts/(\d+)/(\d+)/(\d+)\.html", u).group(1,2,3), reverse=True)
    return unique[0]


def translate(text: str) -> str:
    if not text:
        return ""
    # Split into chunks of ~1500 chars
    chunks, current = [], ""
    for para in text.split("。"):
        para += "。"
        if len(current) + len(para) <= 1500:
            current += para
        else:
            if current:
                chunks.append(current.strip())
            current = para
    if current.strip():
        chunks.append(current.strip())

    translated = []
    for i, chunk in enumerate(chunks):
        prompt = f"""你是一個專業日文翻譯。請將以下日文完整翻譯成繁體中文，只輸出翻譯結果，不要有任何其他解釋或標記。

{chunk}"""
        payload = json.dumps({
            "model": "MiniMax-Text-01",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000
        }).encode()
        # Write payload to temp file to avoid shell escaping issues
        payload_file = "/tmp/trans_payload.json"
        with open(payload_file, "wb") as f:
            f.write(payload)
        result = subprocess.run(
            ["curl", "-s", "-X", "POST",
             "https://api.minimaxi.com/v1/chat/completions",
             "-H", "Content-Type: application/json",
             "-H", f"Authorization: Bearer {MINIMAX_API_KEY}",
             "-d", f"@{payload_file}"],
            capture_output=True, text=True, timeout=60
        )
        try:
            data = json.loads(result.stdout)
            result_text = data["choices"][0]["message"]["content"].strip()
            translated.append(result_text)
        except Exception as e:
            print(f"ERROR translating chunk {i}: {e} | resp: {result.stdout[:200]}", file=sys.stderr)
            translated.append(f"[翻譯失敗]")
    return "\n\n".join(translated)


if __name__ == "__main__":
    article_url = get_latest_article_url()
    print(f"Fetching: {article_url}")
    html = fetch(article_url)
    title = extract_title(html)
    original_text = extract_content(html)
    if not original_text:
        print("ERROR: Could not extract article content", file=sys.stderr)
        sys.exit(1)
    print(f"Title: {title}")
    print(f"Original text length: {len(original_text)} chars")
    print("Translating...")
    translated = translate(original_text)
    print(f"Translated length: {len(translated)} chars")
    # Output JSON for next step
    result = {
        "url": article_url,
        "title": title,
        "original": original_text,
        "translated": translated,
        "fetched_at": datetime.now().isoformat()
    }
    print("---JSON_OUTPUT---")
    print(json.dumps(result, ensure_ascii=False))
