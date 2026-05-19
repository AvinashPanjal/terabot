import asyncio
import os
import re
import httpx
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

from urllib.parse import quote

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = os.getenv("PORT", "8000")
API_ENDPOINT = f"http://127.0.0.1:{PORT}/api/extract"
PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL") or f"http://localhost:{PORT}"
MAX_FILE_SIZE = 2000000000 if os.getenv("TELEGRAM_LOCAL_API_URL") else 50000000

# Regex to find Terabox domains
TERABOX_REGEX = r"https?:\/\/(www\.)?(terabox\.com|teraboxapp\.com|1024tera\.com|nephobox\.com|4funbox\.com|mirrobox\.com|momerybox\.com|teraboxlink\.com|terafileshare\.com)[^\s]+"

def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            ndus TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_user_ndus(user_id: str) -> str:
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT ndus FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def save_user_ndus(user_id: str, ndus: str):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, ndus) VALUES (?, ?)", (user_id, ndus))
    conn.commit()
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to TeraFetch Bot!\n\n"
        "Send me a TeraBox link and I'll extract and download the video directly into this chat for you.\n\n"
        "🔑 **Use your own TeraBox account**:\n"
        "To bypass public download limits, you can link your own TeraBox account using `/login`.\n"
        "To unlink, use `/logout`.\n\n"
        "*(Note: Telegram limits bot uploads to 50MB max)*",
        parse_mode="Markdown"
    )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if not context.args:
        await update.message.reply_text(
            "🔑 **How to link your own TeraBox account:**\n\n"
            "1. Log in to TeraBox on your PC or mobile browser.\n"
            "2. Open Developer Tools (F12 on PC) -> Application -> Cookies.\n"
            "3. Find the cookie named `ndus` and copy its value.\n"
            "4. Send it to the bot like this:\n"
            "`/login your_ndus_cookie_here`",
            parse_mode="Markdown"
        )
        return

    ndus = context.args[0].strip()
    save_user_ndus(user_id, ndus)
    await update.message.reply_text(
        "✅ **Login successful!**\nYour personal TeraBox account has been linked to this chat. "
        "Any links you send will now be extracted using your own account, completely bypassing global limits!",
        parse_mode="Markdown"
    )

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("👋 You have successfully unlinked your TeraBox account from this bot.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text or update.message.caption
    if not text:
        return

    full_urls = re.findall(r"(https?://[^\s]+)", text)
    terabox_urls = [u for u in full_urls if any(d in u for d in ["terabox", "1024tera", "nephobox", "4funbox", "mirrobox", "momerybox", "terafileshare"])]

    if not terabox_urls:
        return

    user_id = str(update.effective_user.id)
    user_ndus = get_user_ndus(user_id)

    for url in terabox_urls:
        status_msg = await update.message.reply_text(f"🔍 Extracting video from link: {url}\nThis might take up to 20 seconds...")
        
        try:
            async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
                payload = {"url": url}
                if user_ndus:
                    payload["ndus"] = user_ndus
                    
                res = await client.post(API_ENDPOINT, json=payload)
                
                if res.status_code != 200:
                    error_detail = res.json().get("detail", "Unknown error")
                    await status_msg.edit_text(f"❌ Failed to extract: {error_detail}")
                    continue
                
                data = res.json()
                direct_url = data.get("directUrl")
                filename = data.get("filename", "video.mp4")
                cookies = data.get("cookies", "")

                if not direct_url:
                    await status_msg.edit_text("❌ Could not find a valid video stream in that link.")
                    continue

                await status_msg.edit_text("⏳ Downloading video securely to server...")

                temp_filename = f"temp_{update.message.message_id}.mp4"
                
                if ".m3u8" in direct_url or "type=M3U8" in direct_url:
                    await status_msg.edit_text("⏳ Stitching video chunks with yt-dlp... (This might take a minute)")
                    
                    process = await asyncio.create_subprocess_exec(
                        'yt-dlp', direct_url, 
                        '--add-header', 'Referer: https://www.terabox.app/', 
                        '--add-header', f'Cookie: {cookies}', 
                        '-o', temp_filename,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    
                    if process.returncode != 0:
                        error_msg = stderr.decode() if stderr else "Unknown error"
                        await status_msg.edit_text(f"❌ yt-dlp failed to stitch the video:\n`{error_msg[-500:]}`", parse_mode="Markdown")
                        continue
                        
                    file_size = os.path.getsize(temp_filename)
                    if file_size > MAX_FILE_SIZE:
                        encoded_filename = quote(filename)
                        download_link = f"{PUBLIC_URL}/api/download?local_file={temp_filename}&filename={encoded_filename}"
                        await status_msg.edit_text(
                            f"⚠️ **File is too large to send directly on Telegram ({file_size/1000000:.1f} MB)**\n"
                            f"Telegram limits bots to sending files under {MAX_FILE_SIZE/1000000:.0f}MB.\n\n"
                            f"👉 You can download it directly here:\n"
                            f"📥 [Download Video]({download_link})",
                            parse_mode="Markdown"
                        )
                        continue
                else:
                    headers_dl = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Cookie": cookies,
                        "Referer": "https://www.terabox.app/"
                    }
                    async with client.stream("GET", direct_url, headers=headers_dl) as stream_res:
                        if stream_res.status_code != 200:
                            await status_msg.edit_text(f"❌ Failed to download video stream (HTTP {stream_res.status_code})")
                            continue
                            
                        content_length = stream_res.headers.get("Content-Length")
                        if content_length and int(content_length) > MAX_FILE_SIZE:
                            mb_size = int(content_length) / 1000000
                            encoded_url = quote(direct_url)
                            encoded_filename = quote(filename)
                            encoded_cookies = quote(cookies)
                            download_link = f"{PUBLIC_URL}/api/download?url={encoded_url}&filename={encoded_filename}&cookies={encoded_cookies}"
                            
                            await status_msg.edit_text(
                                f"⚠️ **File is too large to send directly on Telegram ({mb_size:.1f} MB)**\n"
                                f"Telegram limits bots to sending files under {MAX_FILE_SIZE/1000000:.0f}MB.\n\n"
                                f"👉 You can download it directly here:\n"
                                f"📥 [Download Video]({download_link})",
                                parse_mode="Markdown"
                            )
                            continue

                        with open(temp_filename, "wb") as f:
                            async for chunk in stream_res.aiter_bytes(chunk_size=8192):
                                f.write(chunk)
                
                await status_msg.edit_text("🚀 Uploading to Telegram...")

                with open(temp_filename, "rb") as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        caption=f"🎥 Downloaded Successfully!\nLink: {url}"
                    )
                
                await status_msg.delete()
                os.remove(temp_filename)

        except Exception as e:
            await status_msg.edit_text(f"❌ An error occurred: {str(e)}")
            if os.path.exists(f"temp_{update.message.message_id}.mp4"):
                os.remove(f"temp_{update.message.message_id}.mp4")

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is missing from .env file!")
        return

    print("Starting Telegram Bot...")
    local_api_url = os.getenv("TELEGRAM_LOCAL_API_URL")
    if local_api_url:
        print(f"Using Local Bot API Server: {local_api_url}")
        app = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .base_url(f"{local_api_url}/bot")
            .base_file_url(f"{local_api_url}/file/bot")
            .local_mode(True)
            .build()
        )
    else:
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("logout", logout))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message))

    print("Bot is polling for messages. Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    main()
