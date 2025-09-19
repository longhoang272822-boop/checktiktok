import os, re, asyncio, hashlib
from datetime import datetime
from dotenv import load_dotenv
import aiosqlite
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from playwright.async_api import async_playwright

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
DB_PATH = "videos.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE,
            author TEXT, title TEXT,
            views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER,
            desc_sha1 TEXT, removed_flag INTEGER,
            created_at TEXT
        )""")
        await db.commit()

def sha1_hex(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def verdict(flag: bool) -> str:
    return "❌" if flag else "✅"

async def analyze_tiktok(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        try:
            resp = await page.goto(url, wait_until="networkidle", timeout=20000)
        except:
            await browser.close()
            return {"error": "Không tải được trang."}

        html = await page.content()
        j = await page.evaluate("""() => window.__NEXT_DATA__ || null""")
        parsed = {"title": None,"author": None,"views":0,"likes":0,"comments":0,"shares":0,"removed_flag":0}
        if j:
            try:
                item = j["props"]["pageProps"]["itemInfo"]["itemStruct"]
                parsed["title"] = item.get("desc")
                parsed["author"] = item.get("author")
                parsed["views"] = int(item["stats"]["playCount"])
                parsed["likes"] = int(item["stats"]["diggCount"])
                parsed["comments"] = int(item["stats"]["commentCount"])
                parsed["shares"] = int(item["stats"]["shareCount"])
            except: pass

        if resp.status >= 400 or "unavailable" in html.lower():
            parsed["removed_flag"] = 1
        await browser.close()

    desc_sha1 = sha1_hex((parsed["title"] or "").encode())
    await save_video(url, parsed["author"], parsed["title"], parsed["views"], parsed["likes"],
                     parsed["comments"], parsed["shares"], desc_sha1, parsed["removed_flag"])
    return parsed

async def save_video(url, author, title, views, likes, comments, shares, desc_sha1, removed_flag):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""INSERT OR REPLACE INTO videos
            (url, author, title, views, likes, comments, shares, desc_sha1, removed_flag, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (url, author, title, views, likes, comments, shares, desc_sha1, removed_flag, datetime.utcnow().isoformat()))
        await db.commit()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Gửi link TikTok để phân tích ✅/❌")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if "tiktok.com" not in url:
        await update.message.reply_text("Hãy gửi link TikTok hợp lệ.")
        return
    await update.message.reply_text("⏳ Đang phân tích...")
    res = await analyze_tiktok(url)
    if "error" in res:
        await update.message.reply_text("❌ " + res["error"])
        return
    msg = f"""🎥 {res['title'] or '-'}  
👤 {res['author'] or '-'}  
👁 {res['views']} | ❤ {res['likes']} | 💬 {res['comments']} | 🔁 {res['shares']}  

Shadowban: {verdict(res['views']==0 and (res['likes']>0 or res['comments']>0))}  
Gậy: {verdict(res['removed_flag']==1)}  
Tắt tiếng: ✅ (demo)  
Trùng lặp: ✅ (demo)  
"""
    await update.message.reply_text(msg)

async def main():
    await init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
