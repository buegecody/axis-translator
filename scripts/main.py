#!/usr/bin/env python3
"""
Axis Translator — 主流程控制
用法：
  python main.py process # 爬蟲 + 翻譯（寫入 DB）
  python main.py send       # 寄送最新未發送文章
  python main.py all        # process + send
"""

import os
import sys
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path("articles.db")


def cmd_process():
    """爬蟲 + 翻譯"""
    from scraper import AxisScraper
    from translator import process_pending

    scraper = AxisScraper()
    logger.info("📰 Step 1：抓取新文章...")
    new_articles = scraper.run()
    logger.info("   新增 " + str(len(new_articles)) + " 篇")

    logger.info("🤖 Step 2：翻譯待處理文章...")
    done = process_pending(max_articles=20)
    logger.info("   完成 " + str(done) + " 篇")

    total, pending, no_trans, sent = scraper.get_stats()
    logger.info("═" * 45)
    logger.info("📊 資料庫狀態")
    logger.info("  總文章：  " + str(total))
    logger.info("  待寄出：  " + str(pending))
    logger.info("  待翻譯：  " + str(no_trans))
    logger.info("  已寄出：  " + str(sent))
    logger.info("═" * 45)


def cmd_send():
    """寄送 Email"""
    from send_email import main as send_main
    send_main()


def cmd_all():
    cmd_process()
    cmd_send()


if __name__ == "__main__":
    mode = os.environ.get("RUN_MODE", "process" if len(sys.argv) < 2 else sys.argv[1])

    if mode == "process":
        cmd_process()
    elif mode == "send":
        cmd_send()
    elif mode == "all":
        cmd_all()
    else:
        logger.error("未知模式：" + mode)
        logger.info("用法：process | send | all")
        sys.exit(1)