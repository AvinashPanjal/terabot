import asyncio
import os
import re
import httpx
import json
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.request import HTTPXRequest
from dotenv import load_dotenv
from urllib.parse import quote

# Monkeypatch socket to force IPv4 DNS resolution (prevents container IPv6 connection timeouts)
import socket
orig_getaddrinfo = socket.getaddrinfo
def patched_getaddrinfo(*args, **kwargs):
    args_list = list(args)
    if len(args_list) >= 3:
        args_list[2] = socket.AF_INET
    else:
        kwargs['family'] = socket.AF_INET
    return orig_getaddrinfo(*args_list, **kwargs)
socket.getaddrinfo = patched_getaddrinfo

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID")
PORT = os.getenv("PORT", "8000")
API_ENDPOINT = f"http://127.0.0.1:{PORT}/api/extract"
PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL") or f"http://localhost:{PORT}"
# Set 2GB limit if Local Telegram Bot API Server is configured, otherwise 50MB limit for official Bot API
MAX_FILE_SIZE = 2000000000 if os.getenv("TELEGRAM_LOCAL_API_URL") else 50000000
COOKIE_STORE_PATH = os.getenv(
    "TERABOX_COOKIE_STORE",
    os.path.join(os.path.dirname(__file__), "cookie_store.json")
)

# Enforce a 3-minute video duration limit (180 seconds) to ensure lightning-fast downloads
# and guarantee files fit under Telegram's 50MB bot upload limit.
TRIM_DURATION = 180 

# Regex to find Terabox domains
TERABOX_REGEX = r"https?:\/\/(www\.)?(terabox\.com|terabox\.app|teraboxapp\.com|1024tera\.com|nephobox\.com|4funbox\.com|mirrobox\.com|momerybox\.com|teraboxlink\.com|terafileshare\.com|terasharelink\.com|terasharefile\.com|terashare\.link|freeterabox\.com)[^\s]+"

def normalize_ndus(ndus: str | None) -> str | None:
    if not ndus:
        return None
    value = ndus.strip().strip('"').strip("'")
    match = re.search(r"(?:^|;\s*)ndus=([^;]+)", value)
    if match:
        value = match.group(1).strip()
    return value or None

def is_admin(update: Update) -> bool:
    if not TELEGRAM_ADMIN_ID or not update.effective_user:
        return False
    admin_id = str(TELEGRAM_ADMIN_ID).strip().strip('"').strip("'")
    return str(update.effective_user.id) == admin_id

def mask_cookie(ndus: str) -> str:
    if len(ndus) <= 12:
        return "***"
    return f"{ndus[:6]}...{ndus[-4:]}"

def load_saved_cookie() -> str | None:
    try:
        if not os.path.exists(COOKIE_STORE_PATH):
            return None
        with open(COOKIE_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return normalize_ndus(data.get("ndus"))
    except Exception as e:
        print(f"Failed to read cookie store: {e}")
        return None

def save_cookie(ndus: str, updated_by: int | None = None):
    os.makedirs(os.path.dirname(COOKIE_STORE_PATH), exist_ok=True)
    temp_path = f"{COOKIE_STORE_PATH}.tmp"
    payload = {
        "ndus": ndus,
        "updated_at": int(time.time()),
        "updated_by": updated_by,
    }
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(temp_path, COOKIE_STORE_PATH)

async def check_cookie_valid(ndus: str) -> bool:
    ndus = normalize_ndus(ndus)
    if not ndus:
        return False
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Cookie": f"ndus={ndus}",
        "Referer": "https://www.terabox.app/"
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for check_url in ("https://www.terabox.app/main", "https://www.1024tera.com/main"):
                res = await client.get(check_url, headers=headers)
                final_url = str(res.url).lower()
                if res.status_code == 200 and "login" not in final_url and "passport" not in final_url:
                    return True
                print(f"Cookie validation failed for {check_url}: status={res.status_code}, final_url={final_url}")
    except Exception as e:
        print(f"Cookie validation failed with exception: {e}")
    return False

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to TeraFetch Bot!\n\n"
        "Send me a TeraBox link (or any of its mirror domains like terasharefile, freeterabox, etc.), and I'll extract, download, and send the video directly into this chat for you.\n\n"
        "⚡ **Fast & Unlimited (Full Video downloading enabled!)**",
        parse_mode="Markdown"
    )

async def setcookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    print(f"Received /setcookie request from user {update.effective_user.id if update.effective_user else None} with args={context.args}")
    if not TELEGRAM_ADMIN_ID:
        await update.message.reply_text("Cookie updates are disabled. Set TELEGRAM_ADMIN_ID first.")
        return
    if not is_admin(update):
        print(f"Setcookie validation failed: Admin ID is '{TELEGRAM_ADMIN_ID}', user ID is '{update.effective_user.id if update.effective_user else None}'")
        await update.message.reply_text("You are not allowed to update the TeraBox cookie.")
        return

    args = list(context.args)
    force = False
    if args and args[0].lower() == "force":
        force = True
        args = args[1:]

    raw_cookie = " ".join(args).strip()
    ndus = normalize_ndus(raw_cookie)
    if not ndus:
        await update.message.reply_text(
            "Send the command like this:\n"
            "/setcookie ndus=YOUR_COOKIE_VALUE\n\n"
            "If verification is failing but you want to force save it:\n"
            "/setcookie force ndus=YOUR_COOKIE_VALUE"
        )
        return

    if not force:
        status_msg = await update.message.reply_text("Checking the cookie with TeraBox...")
        if not await check_cookie_valid(ndus):
            await status_msg.edit_text(
                "❌ That cookie did not validate.\n\n"
                "If you are sure this cookie is correct and want to bypass this check, send:\n"
                f"`/setcookie force ndus={ndus}`",
                parse_mode="Markdown"
            )
            return
    else:
        status_msg = await update.message.reply_text("Saving cookie (forced verification bypass)...")

    save_cookie(ndus, updated_by=update.effective_user.id if update.effective_user else None)
    await status_msg.edit_text(
        f"Saved new TeraBox cookie: {mask_cookie(ndus)}\n"
        "The extractor will use it on the next download request."
    )

async def cookie_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    if not is_admin(update):
        await update.message.reply_text("You are not allowed to view cookie status.")
        return

    ndus = load_saved_cookie()
    if not ndus:
        await update.message.reply_text("No saved TeraBox cookie found yet.")
        return

    is_valid = await check_cookie_valid(ndus)
    status = "valid" if is_valid else "expired or rejected"
    await update.message.reply_text(f"Saved cookie {mask_cookie(ndus)} is {status}.")

async def process_single_url(url: str, update: Update):
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

            await status_msg.edit_text("⏳ Downloading video stream... (Speed Boost Active)")

            # Use yt-dlp to download the stream/video file natively
            cmd = [
                'yt-dlp', direct_url,
                '--add-header', 'Referer: https://www.terabox.app/',
            ]
            if cookies:
                cmd += ['--add-header', f'Cookie: {cookies}']
            
            cmd += [
                '--concurrent-fragments', '8',
                '-o', temp_filename
            ]
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                # 30-minute timeout for large videos (e.g. 1GB+)
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=1800.0)
                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    await status_msg.edit_text(f"❌ Failed to download the video:\n`{error_msg[-500:]}`", parse_mode="Markdown")
                    return
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except:
                    pass
                await status_msg.edit_text("❌ Video download timed out after 30 minutes.")
                return
                
            if not os.path.exists(temp_filename) or os.path.getsize(temp_filename) == 0:
                await status_msg.edit_text("❌ Downloaded file was empty or not found.")
                return

            local_api_url = os.getenv("TELEGRAM_LOCAL_API_URL")
            max_size_allowed = 2000000000 if local_api_url else 50000000
                
            file_size = os.path.getsize(temp_filename)
            if file_size > max_size_allowed:
                encoded_filename = quote(filename)
                encoded_url = quote(direct_url)
                encoded_cookies = quote(cookies)
                player_link = f"{PUBLIC_URL}/player?url={encoded_url}&cookies={encoded_cookies}&filename={encoded_filename}"
                download_link = f"{PUBLIC_URL}/api/download?url={encoded_url}&cookies={encoded_cookies}&filename={encoded_filename}"
                limit_mb = max_size_allowed / 1000000
                await status_msg.edit_text(
                    f"⚠️ **File size ({file_size/1000000:.1f} MB) exceeds Telegram bot upload limits ({limit_mb:.0f} MB)**\n\n"
                    f"👉 You can watch or download it directly in your browser:\n"
                    f"🎥 [Stream & Watch Video]({player_link})\n"
                    f"📥 [Direct Download]({download_link})",
                    parse_mode="Markdown"
                )
                if os.path.exists(temp_filename):
                    os.remove(temp_filename)
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
    terabox_urls = [u for u in full_urls if any(d in u for d in ["terabox", "1024tera", "nephobox", "4funbox", "mirrobox", "momerybox", "terafileshare", "terashare", "freeterabox"])]

    if not terabox_urls:
        return

    for url in terabox_urls:
        asyncio.create_task(process_single_url(url, update))

def main():
    import time
    print("Waiting 5 seconds for network interface to stabilize...")
    time.sleep(5)
    
    # Initialize static-ffmpeg to download and add ffmpeg/ffprobe to system PATH
    try:
        import static_ffmpeg
        print("Initializing static-ffmpeg...")
        static_ffmpeg.add_paths()
        print("static-ffmpeg initialized successfully.")
    except Exception as ffmpeg_err:
        print(f"Warning: Failed to initialize static-ffmpeg: {ffmpeg_err}")
    
    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is missing from .env file!")
        return

    # Check if bot polling is explicitly disabled
    if os.getenv("DISABLE_BOT_POLLING") == "true":
        print("⚠️ Bot polling is explicitly disabled via DISABLE_BOT_POLLING environment variable.")
        import time
        while True:
            time.sleep(3600)

    print("Starting Telegram Bot...")
    local_api_url = os.getenv("TELEGRAM_LOCAL_API_URL")
    transport = httpx.AsyncHTTPTransport(retries=3)
    request_config = HTTPXRequest(
        connect_timeout=20.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=5.0,
        media_write_timeout=60.0,
        httpx_kwargs={"transport": transport}
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
    app.add_handler(CommandHandler("setcookie", setcookie, block=False))
    app.add_handler(CommandHandler("cookiestatus", cookie_status, block=False))
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message, block=False))

    print("Bot is polling for messages. Press Ctrl+C to stop.")
    app.run_polling(bootstrap_retries=5)

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    main()
