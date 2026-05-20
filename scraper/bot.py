import asyncio
import os
import re
import httpx
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
PORT = os.getenv("PORT", "8000")
API_ENDPOINT = f"http://127.0.0.1:{PORT}/api/extract"
PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL") or f"http://localhost:{PORT}"
MAX_FILE_SIZE = 50000000

# Enforce a 3-minute video duration limit (180 seconds) to ensure lightning-fast downloads
# and guarantee files fit under Telegram's 50MB bot upload limit.
TRIM_DURATION = 180 

# Regex to find Terabox domains
TERABOX_REGEX = r"https?:\/\/(www\.)?(terabox\.com|terabox\.app|teraboxapp\.com|1024tera\.com|nephobox\.com|4funbox\.com|mirrobox\.com|momerybox\.com|teraboxlink\.com|terafileshare\.com|terasharelink\.com|terasharefile\.com|terashare\.link|freeterabox\.com)[^\s]+"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to TeraFetch Bot!\n\n"
        "Send me a TeraBox link (or any of its mirror domains like terasharefile, freeterabox, etc.), and I'll extract and download the video preview/trimmed version directly into this chat for you.\n\n"
        "⚡ **Fast & Unlimited (No Login/Cookies Required)**",
        parse_mode="Markdown"
    )

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
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300.0)
                if process.returncode != 0:
                    error_msg = stderr.decode() if stderr else "Unknown error"
                    await status_msg.edit_text(f"❌ Failed to download the video:\n`{error_msg[-500:]}`", parse_mode="Markdown")
                    return
            except asyncio.TimeoutError:
                try:
                    process.kill()
                except:
                    pass
                await status_msg.edit_text("❌ Video download timed out after 5 minutes.")
                return
                
            if not os.path.exists(temp_filename) or os.path.getsize(temp_filename) == 0:
                await status_msg.edit_text("❌ Downloaded file was empty or not found.")
                return

            # Trim the local file to TRIM_DURATION using ffmpeg locally
            await status_msg.edit_text(f"⏳ Trimming video to {TRIM_DURATION // 60} minutes...")
            trimmed_filename = temp_filename.replace(".mp4", "_trimmed.mp4")
            trim_cmd = [
                'ffmpeg', '-y',
                '-i', temp_filename,
                '-t', str(TRIM_DURATION),
                '-c', 'copy',
                trimmed_filename
            ]
            
            trim_process = await asyncio.create_subprocess_exec(
                *trim_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout_t, stderr_t = await trim_process.communicate()
            
            if trim_process.returncode == 0 and os.path.exists(trimmed_filename) and os.path.getsize(trimmed_filename) > 0:
                # Replace the original temp_filename with the trimmed one
                os.remove(temp_filename)
                os.rename(trimmed_filename, temp_filename)
                print("Video successfully trimmed locally.")
            else:
                trim_err = stderr_t.decode() if stderr_t else "Unknown error"
                print(f"Warning: Failed to trim video locally: {trim_err}. Using untrimmed version.")
                if os.path.exists(trimmed_filename):
                    try:
                        os.remove(trimmed_filename)
                    except:
                        pass
                
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
    app.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, handle_message, block=False))

    print("Bot is polling for messages. Press Ctrl+C to stop.")
    app.run_polling(bootstrap_retries=5)

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    main()
