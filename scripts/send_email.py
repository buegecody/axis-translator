#!/usr/bin/env python3
"""Send latest translated article via email."""

import sys
import smtplib
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

GMAIL_USER = "liaonaixue@gmail.com"
GMAIL_APP_PASSWORD = "uebwoabvuyahabsr"
TO_EMAIL = "buege1216@gmail.com"

def send_email(title: str, original_url: str, translated: str, date: str):
    # Preserve paragraph structure - split on double newlines, strip each
    paragraphs = [p.strip() for p in translated.split("\n\n") if p.strip()]
    # Clean HTML tags within each paragraph
    cleaned = []
    for p in paragraphs:
        p = re.sub(r"<[^>]+>", "", p)
        p = re.sub(r"[ \t]+", " ", p)
        if p:
            cleaned.append(p)

    sep = "-" * 40
    body_lines = [
        f"Axis Translator 每日譯文",
        f"",
        f"📅 {date}",
        f"📄 {title}",
        f"",
        f"🔗 原文：{original_url}",
        f"",
        f"{sep}",
        f"",
    ]
    for p in cleaned:
        body_lines.append(p)
        body_lines.append("")

    body_lines.extend([
        f"{sep}",
        f"",
        f"由 Axis Translator 自動發送",
    ])

    body = "\n".join(body_lines)

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg["Subject"] = f"【Axis Translator】{title}"

    msg.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
        print(f"Email sent to {TO_EMAIL}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR sending email: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    data = sys.stdin.read()
    idx = data.find("---JSON_OUTPUT---")
    if idx == -1:
        print("No JSON_OUTPUT, skipping email", file=sys.stderr)
        sys.exit(0)
    json_str = data[idx + len("---JSON_OUTPUT---"):].strip()
    article = json.loads(json_str)

    title = article["title"]
    url = article["url"]
    translated = article["translated"]

    m = re.search(r"/posts/(\d{4})/(\d{2})/(\d{2})/", url)
    date = f"{m.group(1)}/{m.group(2)}/{m.group(3)}" if m else datetime.now().strftime("%Y/%m/%d")

    send_email(title, url, translated, date)
