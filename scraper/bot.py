import asyncio
import os
import re
import httpx
import sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from dotenv import load_dotenv

from urllib.parse import quote

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PORT = os.getenv("PORT", "8000")
API_ENDPOINT = f"http://127.0.0.1:{PORT}/api/extract"
PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL") or f"http://localhost:{PORT}"
MAX_FILE_SIZE = 50000000

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

async def download_file_concurrently(url, headers, file_path, status_msg, total_bytes, num_connections=8):
    import math
    chunk_size = math.ceil(total_bytes / num_connections)
    downloaded_bytes = [0] * num_connections
    last_update = [asyncio.get_event_loop().time()]
    
    async def download_part(part_index):
        start = part_index * chunk_size
        end = min(start + chunk_size - 1, total_bytes - 1)
        if start > end:
            return
            
        part_headers = headers.copy()
        part_headers["Range"] = f"bytes={start}-{end}"
        part_file_path = f"{file_path}.part{part_index}"
        
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("GET", url, headers=part_headers) as res:
                if res.status_code != 206:
                    raise Exception(f"Part {part_index} failed with status {res.status_code} (range requests not supported or blocked)")
                
                with open(part_file_path, "wb") as pf:
                    async for chunk in res.aiter_bytes(chunk_size=16384):
                        pf.write(chunk)
                        downloaded_bytes[part_index] += len(chunk)
                        
                        total_downloaded = sum(downloaded_bytes)
                        current_time = asyncio.get_event_loop().time()
                        if current_time - last_update[0] > 4.0:
                            last_update[0] = current_time
                            percent = (total_downloaded / total_bytes * 100) if total_bytes else 0
                            mb_downloaded = total_downloaded / 1000000
                            mb_total = total_bytes / 1000000
                            progress_text = (
                                f"⚡ **Downloading with Multi-Connection (Speed Boost Active)**...\n"
                                f"`[{'█' * int(percent // 10)}{'░' * (10 - int(percent // 10))}]` {percent:.1f}%\n"
                                f"🔹 {mb_downloaded:.1f} MB / {mb_total:.1f} MB"
                            )
                            try:
                                await status_msg.edit_text(progress_text, parse_mode="Markdown")
                            except Exception:
                                pass

    try:
        tasks = [download_part(i) for i in range(num_connections)]
        await asyncio.gather(*tasks)
        
        # Concatenate parts
        with open(file_path, "wb") as outfile:
            for i in range(num_connections):
                part_file_path = f"{file_path}.part{i}"
                if os.path.exists(part_file_path):
                    with open(part_file_path, "rb") as infile:
                        outfile.write(infile.read())
                    os.remove(part_file_path)
    except Exception as e:
        # Clean up any partial files
        for i in range(num_connections):
            part_file_path = f"{file_path}.part{i}"
            if os.path.exists(part_file_path):
                try:
                    os.remove(part_file_path)
                except:
                    pass
        raise e

async def process_single_url(url: str, update: Update, user_ndus: str | None):
    import uuid
    task_id = str(uuid.uuid4())[:8]
    temp_filename = f"/tmp/temp_{update.message.message_id}_{task_id}.mp4"
    
    try:
        status_msg = await update.message.reply_text(f"🔍 Extracting video from link: {url}\nThis might take up to 20 seconds...")
    except Exception as e:
        print(f"Failed to send initial status message for {url}: {e}")
        return
    
    try:
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            payload = {"url": url}
            if user_ndus:
                payload["ndus"] = user_ndus
                
            res = await client.post(API_ENDPOINT, json=payload)
            
            if res.status_code != 200:
                error_detail = res.json().get("detail", "Unknown error")
                await status_msg.edit_text(f"❌ Failed to extract: {error_detail}")
                return
            
            data = res.json()
            direct_url = data.get("directUrl")
            filename = data.get("filename", "video.mp4")
            cookies = data.get("cookies", "")

            if not direct_url:
                await status_msg.edit_text("❌ Could not find a valid video stream in that link.")
                return

            await status_msg.edit_text("⏳ Downloading video securely to server...")

            if ".m3u8" in direct_url or "type=M3U8" in direct_url:
                await status_msg.edit_text("⏳ Stitching video chunks with yt-dlp... (This might take a minute)")
                
                process = await asyncio.create_subprocess_exec(
                    'yt-dlp', direct_url, 
                    '--add-header', 'Referer: https://www.terabox.app/', 
                    '--add-header', f'Cookie: {cookies}', 
                    '--concurrent-fragments', '8',
                    '-o', temp_filename,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                try:
                    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300.0)
                    if process.returncode != 0:
                        error_msg = stderr.decode() if stderr else "Unknown error"
                        await status_msg.edit_text(f"❌ yt-dlp failed to stitch the video:\n`{error_msg[-500:]}`", parse_mode="Markdown")
                        return
                except asyncio.TimeoutError:
                    try:
                        process.kill()
                    except:
                        pass
                    await status_msg.edit_text("❌ Video stitching with yt-dlp timed out after 5 minutes.")
                    return
                    
                file_size = os.path.getsize(temp_filename)
                if file_size > MAX_FILE_SIZE:
                    encoded_filename = quote(filename)
                    download_link = f"{PUBLIC_URL}/api/download?local_file={temp_filename}&filename={encoded_filename}"
                    await status_msg.edit_text(
                        f"⚠️ **File is too large to send directly on Telegram ({file_size/1000000:.1f} MB)**\n"
                        f"Telegram limits bots to sending files under {MAX_FILE_SIZE/1000000:.0f}MB.\n\n"
                        f"👉 You can stream/play or download it directly:\n"
                        f"🎥 [Stream & Watch Video]({download_link})\n"
                        f"📥 [Download Video]({download_link})",
                        parse_mode="Markdown"
                    )
                    return
            else:
                headers_dl = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Cookie": cookies,
                    "Referer": "https://www.terabox.app/"
                }
                
                content_length = None
                use_concurrent = False
                
                try:
                    async with client.stream("GET", direct_url, headers=headers_dl) as stream_res:
                        if stream_res.status_code == 200:
                            content_length_val = stream_res.headers.get("Content-Length")
                            if content_length_val:
                                content_length = int(content_length_val)
                                if content_length > 10000000:
                                    use_concurrent = True
                        else:
                            await status_msg.edit_text(f"❌ Failed to download video stream (HTTP {stream_res.status_code})")
                            return
                except Exception as e:
                    print(f"Error inspecting headers: {e}")

                if use_concurrent and content_length:
                    if content_length > MAX_FILE_SIZE:
                        mb_size = content_length / 1000000
                        encoded_url = quote(direct_url)
                        encoded_filename = quote(filename)
                        encoded_cookies = quote(cookies)
                        
                        player_link = f"{PUBLIC_URL}/player?url={encoded_url}&filename={encoded_filename}&cookies={encoded_cookies}"
                        download_link = f"{PUBLIC_URL}/api/download?url={encoded_url}&filename={encoded_filename}&cookies={encoded_cookies}"
                        
                        await status_msg.edit_text(
                            f"⚠️ **File is too large to send directly on Telegram ({mb_size:.1f} MB)**\n"
                            f"Telegram limits bots to sending files under {MAX_FILE_SIZE/1000000:.0f}MB.\n\n"
                            f"👉 You can stream/play or download it directly:\n"
                            f"🎥 [Stream & Watch Video]({player_link})\n"
                            f"📥 [Download Video]({download_link})",
                            parse_mode="Markdown"
                        )
                        return

                    try:
                        await download_file_concurrently(
                            url=direct_url,
                            headers=headers_dl,
                            file_path=temp_filename,
                            status_msg=status_msg,
                            total_bytes=content_length,
                            num_connections=6
                        )
                    except Exception as dl_err:
                        print(f"Concurrent download failed: {dl_err}. Falling back to single connection.")
                        use_concurrent = False

                if not use_concurrent:
                    async with client.stream("GET", direct_url, headers=headers_dl) as stream_res:
                        if stream_res.status_code != 200:
                            await status_msg.edit_text(f"❌ Failed to download video stream (HTTP {stream_res.status_code})")
                            return
                            
                        total_bytes = int(stream_res.headers.get("Content-Length", 0)) or content_length or 0
                        downloaded_bytes = 0
                        last_update_time = asyncio.get_event_loop().time()

                        with open(temp_filename, "wb") as f:
                            async for chunk in stream_res.aiter_bytes(chunk_size=16384):
                                f.write(chunk)
                                downloaded_bytes += len(chunk)
                                
                                if downloaded_bytes > MAX_FILE_SIZE:
                                    break
                                
                                current_time = asyncio.get_event_loop().time()
                                if current_time - last_update_time > 4.0:
                                    last_update_time = current_time
                                    percent = (downloaded_bytes / total_bytes * 100) if total_bytes else 0
                                    mb_downloaded = downloaded_bytes / 1000000
                                    mb_total = total_bytes / 1000000
                                    progress_text = (
                                        f"⏳ Downloading video securely to server...\n"
                                        f"`[{'█' * int(percent // 10)}{'░' * (10 - int(percent // 10))}]` {percent:.1f}%\n"
                                        f"🔹 {mb_downloaded:.1f} MB / {mb_total:.1f} MB"
                                    )
                                    try:
                                        await status_msg.edit_text(progress_text, parse_mode="Markdown")
                                    except Exception:
                                        pass

                        if downloaded_bytes > MAX_FILE_SIZE:
                            try:
                                os.remove(temp_filename)
                            except:
                                pass
                                
                            encoded_url = quote(direct_url)
                            encoded_filename = quote(filename)
                            encoded_cookies = quote(cookies)
                            
                            player_link = f"{PUBLIC_URL}/player?url={encoded_url}&filename={encoded_filename}&cookies={encoded_cookies}"
                            download_link = f"{PUBLIC_URL}/api/download?url={encoded_url}&filename={encoded_filename}&cookies={encoded_cookies}"
                            
                            await status_msg.edit_text(
                                f"⚠️ **File is too large to send directly on Telegram (>{MAX_FILE_SIZE/1000000:.0f} MB)**\n"
                                f"Telegram limits bots to sending files under {MAX_FILE_SIZE/1000000:.0f}MB.\n\n"
                                f"👉 You can stream/play or download it directly:\n"
                                f"🎥 [Stream & Watch Video]({player_link})\n"
                                f"📥 [Download Video]({download_link})",
                                parse_mode="Markdown"
                            )
                            return
            
            await status_msg.edit_text("🚀 Uploading to Telegram...")

            abs_filepath = os.path.abspath(temp_filename)
            local_api_url = os.getenv("TELEGRAM_LOCAL_API_URL")
            
            if local_api_url:
                try:
                    await update.message.reply_video(
                        video=abs_filepath,
                        write_timeout=300,
                        read_timeout=300
                    )
                except Exception as local_err:
                    print(f"Local file sending failed: {local_err}. Trying direct upload...")
                    with open(temp_filename, "rb") as video_file:
                        await update.message.reply_video(
                            video=video_file,
                            write_timeout=300,
                            read_timeout=300
                        )
            else:
                with open(temp_filename, "rb") as video_file:
                    await update.message.reply_video(
                        video=video_file,
                        write_timeout=300,
                        read_timeout=300
                    )
            
            await status_msg.delete()
            try:
                await update.message.delete()
            except Exception:
                pass
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

    except Exception as e:
        try:
            await status_msg.edit_text(f"❌ An error occurred: {str(e)}")
        except:
            pass
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except:
                pass

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
        asyncio.create_task(process_single_url(url, update, user_ndus))

def main():
    import time
    print("Waiting 5 seconds for network interface to stabilize...")
    time.sleep(5)
    
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is missing from .env file!")
        return

    # Auto-detect Render environment and disable polling to prevent double message issues
    if "SPACE_ID" not in os.environ and "SPACE_HOST" not in os.environ:
        if os.getenv("RENDER_EXTERNAL_URL") or os.getenv("RENDER_INSTANCE_ID"):
            print("⚠️ Render environment detected. Disabling bot polling to prevent duplicate message handling.")
            import time
            while True:
                time.sleep(3600)

    print("Starting Telegram Bot...")
    local_api_url = os.getenv("TELEGRAM_LOCAL_API_URL")
    # Use custom timeouts to prevent ConnectTimeout under high concurrency
    request_config = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=5.0,
        media_write_timeout=60.0
    )

    if local_api_url:
        print(f"Using Local Bot API Server: {local_api_url}")
        app = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .base_url(f"{local_api_url}/bot")
            .base_file_url(f"{local_api_url}/file/bot")
            .local_mode(True)
            .request(request_config)
            .build()
        )
    else:
        app = Application.builder().token(TELEGRAM_BOT_TOKEN).request(request_config).build()

    app.add_handler(CommandHandler("start", start, block=False))
    app.add_handler(CommandHandler("login", login, block=False))
    app.add_handler(CommandHandler("logout", logout, block=False))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message, block=False))

    print("Bot is polling for messages. Press Ctrl+C to stop.")
    app.run_polling(bootstrap_retries=5)

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    main()
