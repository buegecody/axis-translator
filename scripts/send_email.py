#!/usr/bin/env python3
"""
Axis Translator — HTML Email 發送。
從 DB 讀取最新未發送文章，寄送精美 HTML 郵件。
"""

import os
import sys
import smtplib
import logging
import sqlite3
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path("articles.db")
GMAIL_USER = os.environ.get("GMAIL_USER", "liaonaixue@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
TO_EMAIL = os.environ.get("TO_EMAIL", "buege1216@gmail.com")


def render_content(text):
    """將純文字翻譯轉為 HTML（保留分段）。"""
    if not text:
        return ""
    # 把 Markdown 圖片語法轉成<img>
    def replace_img(m):
        alt = m.group(1).strip()
        url = m.group(2)
        if "wp-content/uploads" in url:
            result = '<img src="' + url + '" style="max-width:100%;height:auto;margin:12px 0;display:block;border-radius:2px;">'
            if alt and alt not in ("", "Image") and not alt.startswith("Image "):
                result += '<p style="font-size:12px;color:#888780;font-family:Arial,sans-serif;margin:4px 0 12px;">' + alt + '</p>'
            return result
        return ""
    text = re.sub(r'!\[([^\]]*)\]\((https?://[^\)]+)\)', replace_img, text)
    text = re.sub(r'!\[.*?\]', '', text)
    return text


def make_card(i, art):
    url = art.get("url", "#")
    title = art.get("zh_title") or art.get("title", "（無標題）")
    trans = art.get("translation", "")
    meta = art.get("published", "")
    if meta:
        meta = "Axis · " + meta

    translation_html = ""
    if trans:
        trans_html = render_content(trans)
        # 以 \n\n分割段落
        paragraphs = [p.strip() for p in trans_html.split("\n\n") if p.strip()]
        para_htmls = []
        for p in paragraphs:
            if p.startswith("<img"):
                para_htmls.append(p)
            else:
                para_htmls.append("<p>" + p + "</p>")
        translation_html = (
            "<div class=\"section\">"
            "<p class=\"label\">繁體中文全文</p>"
            + "".join(para_htmls)
            + "</div>"
        )
    else:
        translation_html = "<div class=\"section\"><p class=\"body-text\" style=\"color:#b4b2a9\">翻譯生成中...</p></div>"

    kicker = "文章 " + f"{i:02d}"
    card = "<div class=\"card\">"
    card += "<div class=\"card-header\">"
    card += "<p class=\"kicker\">" + kicker + "</p>"
    card += "<h2 class=\"card-title\"><a href=\"" + url + "\">" + title + "</a></h2>"
    card += "<p class=\"card-meta\">" + meta + "</p>"
    card += "</div>"
    card += translation_html
    card += "<div class=\"read-more\"><a href=\"" + url + "\">閱讀原文 →</a></div>"
    card += "</div>"
    return card


CSS = """
<style>
body{margin:0;padding:0;background:#f5f4f0;font-family:Georgia,serif;color:#2c2c2a}
.wrap{max-width:640px;margin:0 auto;padding:24px 16px}
.hd{background:#1a1a18;padding:36px 32px 28px;border-radius:4px 4px 0 0}
.hd-kicker{font-family:Arial,sans-serif;font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:#888780;margin:0 0 10px}
.hd-title{font-size:32px;font-weight:400;color:#f1efe8;margin:0 0 8px;line-height:1.15}
.hd-sub{font-size:14px;color:#888780;margin:0;font-style:italic}
.hd-meta{margin-top:20px;padding-top:16px;border-top:1px solid #333330;font-family:Arial,sans-serif;font-size:12px;color:#5f5e5a}
.intro{background:#2c2c2a;padding:18px 32px}
.intro p{margin:0;font-size:15px;color:#b4b2a9;line-height:1.7;font-style:italic}
.intro strong{color:#f1efe8;font-style:normal}
.card{background:#fff;margin:16px 0;border-radius:2px;border-left:3px solid #1a1a18}
.card-header{padding:22px 28px 14px;border-bottom:1px solid #f1efe8}
.kicker{font-family:Arial,sans-serif;font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:#b4b2a9;margin:0 0 8px}
.card-title{font-size:19px;font-weight:400;margin:0 0 8px;line-height:1.3}
.card-title a{color:#1a1a18;text-decoration:none;border-bottom:1px solid #d3d1c7}
.card-meta{font-family:Arial,sans-serif;font-size:12px;color:#888780;margin:0}
.section{padding:18px 28px;border-bottom:1px solid #f1efe8}
.label{font-family:Arial,sans-serif;font-size:10px;letter-spacing:.2em;text-transform:uppercase;color:#b4b2a9;margin:0 0 10px}
.body-text{font-size:14px;line-height:1.8;color:#444441;margin:0}
.read-more{padding:14px 28px 22px}
.read-more a{font-family:Arial,sans-serif;font-size:12px;color:#1a1a18;text-decoration:none;border-bottom:1px solid #1a1a18}
.ft{background:#1a1a18;padding:24px 32px;border-radius:0 0 4px 4px}
.ft p{font-family:Arial,sans-serif;font-size:11px;color:#5f5e5a;margin:0 0 4px;line-height:1.6}
</style>
"""


def build_html_email(articles):
    now = datetime.now()
    date_str = now.strftime("%Y 年 %m 月 %d 日")
    n = len(articles)
    cards = "".join(make_card(i, art) for i, art in enumerate(articles, 1))

    html = (
        "<!DOCTYPE html><html lang='zh-TW'><head><meta charset='UTF-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1.0'>"
        + CSS +
        "</head><body>"
        "<div class='wrap'>"
        "<div class='hd'>"
        "<p class='hd-kicker'>Axis Translator · 每日譯文</p>"
        "<h1 class='hd-title'>本週藝術與設計<br>精選摘要</h1>"
        "<p class='hd-sub'>由 MiniMax 翻譯，為你直譯日本設計每一篇</p>"
        "<div class='hd-meta'>" + date_str + " &nbsp;·&nbsp; 共 " + str(n) + " 篇文章</div>"
        "</div>"
        "<div class='intro'><p>本期精選 <strong>" + str(n) + "</strong> 篇 Axis 文章，由 AI 完整翻譯。</p></div>"
        + cards +
        "<div class='ft'>"
        "<p>文章來源：axismag.jp &nbsp;·&nbsp; 翻譯由 MiniMax 生成</p>"
        "<p>© " + str(now.year) + " Axis Translator</p>"
        "</div>"
        "</div></body></html>"
    )
    return html


def send_email(subject, html):
    if not GMAIL_APP_PASSWORD:
        logger.error("GMAIL_APP_PASSWORD 未設定")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Axis Translator", GMAIL_USER))
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText("請使用支援 HTML 的郵件客戶端查看。", "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, [TO_EMAIL], msg.as_string())
        logger.info("Email 已寄出至 " + TO_EMAIL)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("Gmail 認證失敗")
    except Exception as e:
        logger.error("寄信失敗：" + str(e))
    return False


def main():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT * FROM articles
            WHERE sent = 0 AND translation IS NOT NULL AND translation != ''
            ORDER BY published DESC LIMIT 3
        """).fetchall()
    articles = [dict(r) for r in rows]

    if not articles:
        logger.info("沒有待發送文章")
        return

    html = build_html_email(articles)
    first_title = articles[0]["zh_title"] or articles[0]["title"]
    subject = "【Axis Translator】" + first_title

    success = send_email(subject, html)
    if success:
        with sqlite3.connect(DB_PATH) as conn:
            conn.executemany(
                "UPDATE articles SET sent = 1 WHERE id = ?",
                [(a["id"],) for a in articles]
            )
            conn.commit()
        logger.info("已更新 " + str(len(articles)) + " 篇為已發送")


if __name__ == "__main__":
    main()