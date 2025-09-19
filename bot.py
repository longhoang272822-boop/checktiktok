import os, re, hashlib
from datetime import datetime
from dotenv import load_dotenv
import aiosqlite

from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
)
from playwright.async_api import async_playwright

# ---------- Config ----------
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_PATH = "videos.db"


# ---------- DB ----------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS videos (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          url TEXT UNIQUE,
          author TEXT,
          title TEXT,
          views INTEGER,
          likes INTEGER,
          comments INTEGER,
          shares INTEGER,
          removed_flag INTEGER,
          desc_sha1 TEXT,
          created_at TEXT
        )""")
        await db.commit()


async def save_row(url, author, title, views, likes, comments, shares, removed_flag, desc_sha1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        INSERT OR REPLACE INTO videos
        (url, author, title, views, likes, comments, shares, removed_flag, desc_sha1, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (url, author, title, views, likes, comments, shares, int(removed_flag),
              desc_sha1, datetime.utcnow().isoformat()))
        await db.commit()


# ---------- Helpers ----------
def sha1_hex(b: bytes) -> str:
    h = hashlib.sha1()
    h.update(b)
    return h.hexdigest()


def verdict(flag_problem: bool) -> str:
    return "❌" if flag_problem else "✅"


# ---------- Core: scrape TikTok page ----------
async def analyze_tiktok(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            resp = await page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            await browser.close()
            return {"error": f"Không tải được trang ({e})."}

        status = resp.status if resp else None
        html = await page.content()
        state = await page.evaluate("""() => window.__NEXT_DATA__ || null""")
        await browser.close()

    parsed = {
        "title": None, "author": None,
        "views": 0, "likes": 0, "comments": 0, "shares": 0,
        "removed_flag": 0
    }

    if state:
        try:
            item = state["props"]["pageProps"]["itemInfo"]["itemStruct"]
            parsed["title"] = item.get("desc")
            parsed["author"] = item.get("author")
            st = item.get("stats") or {}
            parsed["views"] = int(st.get("playCount") or 0)
            parsed["likes"] = int(st.get("diggCount") or 0)
            parsed["comments"] = int(st.get("commentCount") or 0)
            parsed["shares"] = int(st.get("shareCount") or 0)
        except Exception:
            pass

    # detect removed/private/unavailable
    if (status and status >= 400) or ("unavailable" in html.lower()) or ("this video is private" in html.lower()):
        parsed["removed_flag"] = 1

    desc_sha1 = sha1_hex(((parsed["title"] or "").lower()).encode("utf-8"))
    await save_row(url, parsed["author"], parsed["title"], parsed["views"], parsed["likes"],
                   parsed["comments"], parsed["shares"], parsed["removed_flag"], desc_sha1)
    return parsed


# ---------- Telegram handlers ----------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Gửi link TikTok để phân tích ✅/❌")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = (update.message.text or "").strip()
    if "tiktok.com" not in url:
        await update.message.reply_text("Hãy gửi link TikTok hợp lệ (https://www.tiktok.com/...).")
        return
    await update.message.reply_text("⏳ Đang phân tích…")
    res = await analyze_tiktok(url)
    if "error" in res:
        await update.message.reply_text("❌ " + res["error"])
        return

    shadow_flag = (res["views"] == 0 and (res["likes"] > 0 or res["comments"] > 0))
    msg = (
        f"🎥 {res['title'] or '-'}\n"
        f"👤 {res['author'] or '-'}\n"
        f"👁 {res['views']} | ❤ {res['likes']} | 💬 {res['comments']} | 🔁 {res['shares']}\n\n"
        f"Shadow ban: {verdict(shadow_flag)}\n"
        f"Gậy: {verdict(res['removed_flag']==1)}\n"
        f"Tắt tiếng: ✅ (demo)\n"
        f"Trùng lặp: ✅ (demo)\n"
    )
    await update.message.reply_text(msg)


# ---------- Entry (sync) ----------
def main():
    # init DB trước khi khởi chạy PTB (tránh lỗi event loop)
    import asyncio
    asyncio.run(init_db())

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling(close_loop=True)  # PTB tự quản lý event loop


if __name__ == "__main__":
    main()

