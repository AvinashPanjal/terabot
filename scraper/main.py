import os
import sys
import asyncio

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


# Set Playwright browsers path inside the project root for Render compatibility
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pw-browsers")

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel
from playwright.async_api import async_playwright
import uvicorn
import re
import httpx
import time
from urllib.parse import urlparse, parse_qs, unquote
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Terabox Extraction Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

playwright_semaphore = None

class ExtractRequest(BaseModel):
    url: str
    ndus: str | None = None

def extract_surl(url: str) -> str:
    parsed_url = urlparse(url)
    surl = None
    if "surl" in parse_qs(parsed_url.query):
        surl = parse_qs(parsed_url.query)["surl"][0]
    elif "/s/" in parsed_url.path:
        parts = parsed_url.path.split("/s/")
        if len(parts) > 1:
            surl = parts[1].split("/")[0].split("?")[0]
            
    if not surl:
        match = re.search(r"[?&]surl=([a-zA-Z0-9_-]+)", url)
        if match:
            surl = match.group(1)
        else:
            match2 = re.search(r"/s/([a-zA-Z0-9_-]+)", url)
            if match2:
                surl = match2.group(1)
                
    if surl and surl.startswith("1"):
        surl = surl[1:]
    return surl

async def get_browser_cookies() -> dict:
    try:
        async with async_playwright() as p:
            user_data_dir = os.path.join(os.path.dirname(__file__), "browser_session")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"]
            )
            cookies = await context.cookies()
            await context.close()
        return {c['name']: c['value'] for c in cookies}
    except Exception as e:
        print(f"Error fetching cookies from Playwright: {e}")
        return {}

# Parse comma-separated list of cookies
NDUS_POOL = []
ndus_env = os.getenv("TERABOX_NDUS")
if ndus_env:
    NDUS_POOL = [c.strip() for c in ndus_env.split(",") if c.strip()]

# Initialize healthy cookies list with configured cookies
HEALTHY_COOKIES = list(NDUS_POOL)

TERABOX_EMAIL = os.getenv("TERABOX_EMAIL")
TERABOX_PASSWORD = os.getenv("TERABOX_PASSWORD")

credentials_path = os.path.join(os.path.dirname(__file__), "credentials.json")
if os.path.exists(credentials_path):
    try:
        import json
        with open(credentials_path, "r", encoding="utf-8") as f:
            creds = json.load(f)
            if not TERABOX_EMAIL:
                TERABOX_EMAIL = creds.get("TERABOX_EMAIL")
            if not TERABOX_PASSWORD:
                TERABOX_PASSWORD = creds.get("TERABOX_PASSWORD")
    except Exception as e:
        print(f"Error loading credentials.json: {e}")

CURRENT_NDUS = HEALTHY_COOKIES[0] if HEALTHY_COOKIES else None

async def check_cookie_valid(ndus: str) -> bool:
    if not ndus:
        return False
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": f"ndus={ndus}",
            "Referer": "https://www.terabox.app/"
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            res = await client.get("https://www.terabox.app/main", headers=headers)
            if res.status_code == 200 and "login" not in str(res.url):
                return True
    except Exception as e:
        print(f"Error checking cookie validity: {e}")
    return False

async def login_and_get_cookie(email: str, password: str) -> str | None:
    global browser_context, playwright_instance
    if not email or not password:
        print("Credentials not configured. Skipping automated login.")
        return None
    print(f"Attempting automated login for {email}...")
    try:
        if not browser_context:
            print("browser_context not ready in login, initializing now...")
            if not playwright_instance:
                playwright_instance = await async_playwright().start()
            user_data_dir = os.path.join(os.path.dirname(__file__), "browser_session")
            browser_context = await playwright_instance.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                viewport={"width": 375, "height": 812},
                args=[
                    "--autoplay-policy=no-user-gesture-required", 
                    "--mute-audio",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-web-security"
                ],
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            )
            
        page = await browser_context.new_page()
        


        try:
            # Navigate with retries to handle startup bandwidth saturation (e.g. static-ffmpeg download)
            for attempt in range(2):
                try:
                    print(f"Navigating to login page (attempt {attempt+1})...")
                    await page.goto("https://www.1024tera.com/wap/outside/login", wait_until="domcontentloaded", timeout=30000)
                    break
                except Exception as goto_err:
                    if attempt == 1:
                        raise goto_err
                    print(f"Navigation attempt {attempt+1} failed: {goto_err}. Retrying in 4 seconds...")
                    await page.wait_for_timeout(4000)
            await page.wait_for_timeout(3000)
            
            # Wait for any of the key elements to mount
            try:
                print("Waiting for login elements to mount...")
                await page.wait_for_selector(".icon-arrow, .other-item, input[placeholder='Enter your email']", timeout=15000)
            except Exception as wait_err:
                print(f"Login elements failed to mount: {wait_err}")

            # Check if email input is already visible
            email_input = await page.query_selector('input[placeholder="Enter your email"]')
            if email_input and await email_input.is_visible():
                print("Email input is already visible, skipping navigation clicks.")
            else:
                # Check if we need to expand options
                arrow = await page.query_selector(".icon-arrow")
                if arrow and await arrow.is_visible():
                    print("Tapping expand arrow...")
                    await arrow.tap()
                    await page.wait_for_timeout(1000)
                    
                # Wait for both envelope buttons to mount/render to avoid race conditions
                other_items = []
                for _ in range(10): # up to 5 seconds
                    other_items = await page.query_selector_all(".other-item")
                    if len(other_items) >= 2:
                        break
                    await page.wait_for_timeout(500)
                    
                if len(other_items) >= 2:
                    print("Tapping the second envelope button (Mail)...")
                    await other_items[1].tap()
                    await page.wait_for_timeout(1500)
                elif len(other_items) == 1:
                    print("Tapping the only envelope button...")
                    await other_items[0].tap()
                    await page.wait_for_timeout(1500)
                else:
                    print("Envelope button (.other-item) not found.")
            
            # Fill email and password
            await page.fill('input[placeholder="Enter your email"]', email)
            await page.fill('input[placeholder="Enter your new password."]', password)
            await page.wait_for_timeout(1000)
            
            # Tap Login
            login_btn = await page.wait_for_selector(".btn-class-login", timeout=5000)
            if login_btn:
                await login_btn.tap()
                print("Automated login submitted. Waiting for session cookies...")
                
                ndus = None
                for _ in range(15):
                    cookies = await browser_context.cookies()
                    ndus_cookie = next((c for c in cookies if c["name"] == "ndus"), None)
                    if ndus_cookie:
                        ndus = ndus_cookie["value"]
                        break
                    await page.wait_for_timeout(1000)
                    
                if ndus:
                    print("Automated login succeeded!")
                    return ndus
                else:
                    err_screenshot = os.path.join(os.path.dirname(__file__), "login_error.png")
                    await page.screenshot(path=err_screenshot)
                    print(f"Automated login failed to get ndus cookie. Saved page state screenshot to {err_screenshot}")
        except Exception as page_err:
            print(f"Error inside Playwright login context: {page_err}")
            try:
                err_screenshot = os.path.join(os.path.dirname(__file__), "login_error.png")
                await page.screenshot(path=err_screenshot)
            except:
                pass
        finally:
            await page.close()
    except Exception as e:
        print(f"Error during automated login: {e}")
    return None

login_lock = asyncio.Lock()

async def ensure_active_cookie() -> str | None:
    global CURRENT_NDUS, HEALTHY_COOKIES, login_lock
    
    # 1. Check if the existing cached cookie is valid
    if CURRENT_NDUS:
        is_valid = await check_cookie_valid(CURRENT_NDUS)
        if is_valid:
            return CURRENT_NDUS
        else:
            print("Current cached ndus cookie has expired/invalidated.")
            CURRENT_NDUS = None
            
    # 2. Check if pool contains a valid cookie
    for ndus in list(HEALTHY_COOKIES):
        is_valid = await check_cookie_valid(ndus)
        if is_valid:
            CURRENT_NDUS = ndus
            return CURRENT_NDUS
            
    # 3. Trigger automated login if credentials are set (guarded by lock)
    if TERABOX_EMAIL and TERABOX_PASSWORD:
        async with login_lock:
            # Re-check if another concurrent request already populated CURRENT_NDUS while we waited for the lock
            if CURRENT_NDUS:
                is_valid = await check_cookie_valid(CURRENT_NDUS)
                if is_valid:
                    return CURRENT_NDUS
            
            new_ndus = await login_and_get_cookie(TERABOX_EMAIL, TERABOX_PASSWORD)
            if new_ndus:
                CURRENT_NDUS = new_ndus
                # Update the cookie lists
                if new_ndus not in HEALTHY_COOKIES:
                    HEALTHY_COOKIES.append(new_ndus)
                return new_ndus
            
    print("Warning: No active or valid ndus cookie could be found or refreshed.")
    return None

async def cleanup_loop():
    while True:
        try:
            folder = os.path.dirname(os.path.abspath(__file__))
            now = time.time()
            for f in os.listdir(folder):
                if f.startswith("temp_") and f.endswith(".mp4"):
                    path = os.path.join(folder, f)
                    if now - os.path.getmtime(path) > 3600: # 1 hour
                        os.remove(path)
                        print(f"Auto-cleaned old temp file: {f}")
        except Exception as e:
            print(f"Error cleaning old temp files: {e}")
        await asyncio.sleep(1800) # Check every 30 minutes

# Playwright global browser context variables
playwright_instance = None
browser_context = None

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_loop())
    
    # Pre-launch Playwright browser context on startup to keep it warm and fast
    global playwright_instance, browser_context
    try:
        print("Pre-launching global Playwright browser context (mobile emulated)...")
        playwright_instance = await async_playwright().start()
        user_data_dir = os.path.join(os.path.dirname(__file__), "browser_session")
        browser_context = await playwright_instance.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            viewport={"width": 375, "height": 812},
            args=[
                "--autoplay-policy=no-user-gesture-required", 
                "--mute-audio",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-web-security"
            ],
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
        )
        print("Global Playwright browser context launched successfully.")
    except Exception as e:
        print(f"Failed to pre-launch global Playwright browser: {e}")

    # Try to verify or refresh cookie on startup (after browser is ready!)
    async def init_cookie_on_startup():
        print("Checking/refreshing cookie on startup...")
        await ensure_active_cookie()
    asyncio.create_task(init_cookie_on_startup())

@app.on_event("shutdown")
async def shutdown_event():
    global playwright_instance, browser_context
    if browser_context:
        try:
            await browser_context.close()
        except:
            pass
    if playwright_instance:
        try:
            await playwright_instance.stop()
        except:
            pass

@app.head("/")
@app.get("/")
async def root():
    return {"status": "healthy", "service": "terabox-downloader"}

@app.get("/api/status")
async def status():
    import socket
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    bot_api_running = False
    try:
        result = sock.connect_ex(('127.0.0.1', 8081))
        if result == 0:
            bot_api_running = True
    except Exception:
        pass
    finally:
        sock.close()
        
    log_content = ""
    try:
        if os.path.exists("/tmp/telegram-bot-api.log"):
            with open("/tmp/telegram-bot-api.log", "r") as f:
                log_content = f.read()[-5000:]
        else:
            log_content = "Log file /tmp/telegram-bot-api.log does not exist."
    except Exception as e:
        log_content = f"Error reading log: {e}"
        
    return {
        "bot_api_running_port_8081": bot_api_running,
        "log_tail": log_content,
        "env_variables": {k: v for k, v in os.environ.items() if "TOKEN" not in k and "HASH" not in k and "API" not in k}
    }

@app.post("/api/extract")
async def extract_url(req: ExtractRequest):
    url = req.url
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    print(f"Extraction request for link: {url}")
    
    # Check and refresh/ensure active cookie
    ndus = await ensure_active_cookie()
    if ndus:
        print(f"Using active ndus cookie ({ndus[:8]}...) for extraction.")
    else:
        print("Proceeding without active cookie (may fall back to 20-second preview).")

    # Playwright Guest-Mode or Logged-In Automation
    direct_url = None
    filename = "video.mp4"
    cookie_string = ""

    global playwright_instance, browser_context, playwright_semaphore
    if playwright_semaphore is None:
        # We increase concurrency to 3 since we share the browser and only open tabs (very lightweight)
        playwright_semaphore = asyncio.Semaphore(3)

    await playwright_semaphore.acquire()
    try:
        # Self-healing logic to relaunch browser if it closed/crashed
        if not browser_context:
            if not playwright_instance:
                playwright_instance = await async_playwright().start()
            user_data_dir = os.path.join(os.path.dirname(__file__), "browser_session")
            browser_context = await playwright_instance.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                args=[
                    "--autoplay-policy=no-user-gesture-required", 
                    "--mute-audio",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-web-security"
                ],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            )

        # Inject ndus cookie into context if available
        if ndus:
            domains = [
                ".terabox.app", 
                ".teraboxapp.com", 
                ".1024tera.com", 
                ".terafileshare.com", 
                ".nephobox.com",
                ".4funbox.com",
                ".mirrobox.com",
                ".momerybox.com",
                ".teraboxlink.com",
                ".terasharelink.com",
                ".terasharefile.com",
                ".terashare.link",
                ".freeterabox.com"
            ]
            await browser_context.add_cookies([{
                "name": "ndus",
                "value": ndus,
                "domain": d,
                "path": "/"
            } for d in domains])
            print("Injected active ndus cookie into Playwright context.")

        page = await browser_context.new_page()
        
        async def handle_request(route, request):
            nonlocal direct_url
            req_url = request.url
            
            # Print intercepted URLs containing relevant keywords for debugging
            if any(kw in req_url.lower() for kw in ["download", "video", "stream", "pcs", "m3u8", ".mp4", "api/szfile", "sharing"]) or request.resource_type == "media":
                print(f"[Intercepted Request] Type: {request.resource_type} | URL: {req_url}")

            req_url_lower = req_url.lower()
            if any(x in req_url_lower for x in [
                "analytics", "googleads", "doubleclick", "facebook.net", "facebook.com", 
                "bat.bing", "bing.com", "beacon", "telemetry"
            ]):
                await route.abort()
                return
            
            if request.resource_type in ["image", "font"]:
                await route.abort()
                return

            if ".ts" in req_url_lower or "_ts/" in req_url_lower:
                await route.abort()
                return

            if "SUBTITLE" in req_url or "subtitle" in req_url or ".srt" in req_url:
                await route.continue_()
                return

            req_url_lower = req_url.lower()
            if "api/download" in req_url_lower or "type=d" in req_url_lower or ".m3u8" in req_url_lower or "type=m3u8" in req_url_lower or "sharing" in req_url_lower or "pcs.baidu.com" in req_url_lower:
                if any(domain in req_url_lower for domain in ["terabox", "baidupcs", "freeterabox", "baidu.com", "pcs", "teraboxcdn"]):
                    if "thumbnail" not in req_url_lower and "favicon" not in req_url_lower:
                        if not direct_url:
                            direct_url = req_url
            await route.continue_()

        await page.route("**/*", handle_request)

        # Pre-resolve redirects using instant URL rewriting to bypass HTTP bottlenecks
        surl = extract_surl(url)
        if surl:
            target_url = f"https://www.1024tera.com/sharing/link?surl={surl}"
            print(f"Pre-resolved {url} -> {target_url}")
        else:
            target_url = url

        print(f"Navigating to {target_url} ...")
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            print("Page loaded.")
        except Exception as e:
            print(f"Playwright error during goto: {e}")

        print("Waiting for direct_url interception...")
        for _ in range(10):
            if direct_url:
                break
            await page.wait_for_timeout(1000)
            
        if not direct_url:
            print("No direct_url yet. Checking if we are in file list view...")
            try:
                file_row = await page.wait_for_selector('.file-name, .file-list-row, .wp-s-core-pan-file-list-item, .wp-s-pan-file-list-row', timeout=5000)
                if file_row:
                    print("Found file list row. Clicking it to open video player...")
                    await file_row.click()
                    await page.wait_for_timeout(2000)
            except Exception:
                print("Did not find file list row.")

        if not direct_url:
            print("Checking for video element...")
            try:
                await page.wait_for_selector("video", timeout=10000)
                print("Video element found! Forcing play and removing dialog blocks...")
                
                # Active background task to remove any overlays/popups and play video
                async def keep_playing():
                    for _ in range(10):
                        if direct_url:
                            break
                        await asyncio.sleep(1.5)
                        try:
                            await page.evaluate("""() => {
                                // Delete/hide any overlay blocks, login dialogs, and masks
                                const classesToHide = ['login', 'modal', 'dialog', 'popup', 'overlay', 'mask', 'passport'];
                                document.querySelectorAll('*').forEach(el => {
                                    if (el && el.className && typeof el.className === 'string') {
                                        if (classesToHide.some(cls => el.className.toLowerCase().includes(cls))) {
                                            if (!el.contains(document.querySelector('video'))) {
                                                el.style.setProperty('display', 'none', 'important');
                                            }
                                        }
                                    }
                                    if (el && el.id && typeof el.id === 'string') {
                                        if (classesToHide.some(cls => el.id.toLowerCase().includes(cls))) {
                                            if (!el.contains(document.querySelector('video'))) {
                                                el.style.setProperty('display', 'none', 'important');
                                            }
                                        }
                                    }
                                });
                                
                                // Force unmute and play the video element
                                const v = document.querySelector('video');
                                if (v) {
                                    v.muted = true;
                                    v.play().catch(() => {});
                                }
                            }""")
                        except:
                            pass
                
                asyncio.create_task(keep_playing())
                
                # Check for direct URL
                for _ in range(15):
                    if direct_url:
                        break
                    # Re-check src attribute if it changed dynamically
                    video_src = await page.evaluate("() => { const v = document.querySelector('video'); return v ? v.src : null; }")
                    if video_src and video_src.startswith("http") and not video_src.startswith("blob"):
                        print(f"Captured direct URL dynamically from video src: {video_src}")
                        direct_url = video_src
                        break
                    await page.wait_for_timeout(1000)
            except Exception as e:
                print(f"Video element error or timeout: {e}")

        if not direct_url:
            print("Checking for Download button as fallback...")
            try:
                dl_btn = await page.wait_for_selector('a.download-btn, a[title="Download"], button[title="Download"], .download-btn', timeout=4000)
                if dl_btn:
                    print("Found download button! Clicking...")
                    try:
                        async with page.expect_download(timeout=6000) as download_info:
                            await dl_btn.click()
                        download = await download_info.value
                        direct_url = download.url
                    except Exception:
                        href = await dl_btn.get_attribute("href")
                        if href and href != "javascript:void(0);":
                            direct_url = href
                        else:
                            await dl_btn.click()
                            await page.wait_for_timeout(2000)
            except Exception:
                print("Download button not found.")
        
        if direct_url and direct_url.startswith("/"):
            direct_url = "https://www.1024tera.com" + direct_url
            
        cookies = await browser_context.cookies()
        cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

        await page.close()
            
    except Exception as e:
        print(f"Playwright error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        playwright_semaphore.release()

    if not direct_url:
        raise HTTPException(status_code=404, detail="Could not extract direct download URL from TeraBox link.")

    return {
        "success": True,
        "directUrl": direct_url,
        "filename": filename,
        "cookies": cookie_string
    }

@app.get("/logs", response_class=HTMLResponse)
async def get_logs():
    import os
    paths_to_check = [
        "/tmp/app.log",
        "app.log",
        "../app.log",
        "/opt/render/project/src/app.log",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "app.log"),
        os.path.join(os.path.dirname(__file__), "app.log")
    ]
    log_file_path = None
    for p in paths_to_check:
        if os.path.exists(p):
            log_file_path = p
            break
            
    if log_file_path:
        try:
            with open(log_file_path, "r", encoding="utf-8") as f:
                content = f.read()
            return f"<html><body><h3>Application Logs (Path: {log_file_path})</h3><pre>{content}</pre></body></html>"
        except Exception as e:
            return f"Error reading logs at {log_file_path}: {e}"
    return f"No logs found. Checked paths: {paths_to_check}"

@app.get("/debug")
async def debug_info():
    import os, sys
    try:
        cwd = os.getcwd()
        cwd_files = os.listdir('.')
        tmp_files = os.listdir('/tmp') if os.path.exists('/tmp') else []
        env_keys = list(os.environ.keys())
        clean_env = {k: ("SET" if os.environ[k] else "EMPTY") for k in env_keys if "TOKEN" in k or "KEY" in k or "COOKIE" in k or "SECRET" in k}
        return {
            "cwd": cwd,
            "cwd_files": cwd_files,
            "tmp_files": tmp_files,
            "python_version": sys.version,
            "environment_keys": env_keys,
            "masked_env": clean_env
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/run_diag")
async def run_diag():
    import os
    from playwright.async_api import async_playwright
    
    results = {}
    try:
        async with async_playwright() as p:
            user_data_dir = os.path.join(os.path.dirname(__file__), "login_session_dump")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                viewport={"width": 375, "height": 812},
                args=[
                    "--autoplay-policy=no-user-gesture-required", 
                    "--mute-audio",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-web-security"
                ],
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
            )
            page = await context.new_page()
            try:
                await page.goto("https://www.1024tera.com/wap/outside/login", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(4000)
                
                # Check for arrow
                arrow = await page.query_selector(".icon-arrow")
                arrow_found = arrow is not None
                if arrow:
                    await arrow.tap()
                    await page.wait_for_timeout(2000)
                
                # Capture screenshot
                diag_screenshot = os.path.join(os.path.dirname(__file__), "diag_tap_result.png")
                await page.screenshot(path=diag_screenshot)
                
                # Dump HTML of body or login container
                body_content = await page.evaluate("""() => {
                    const el = document.querySelector('.wap-login-home') || document.body;
                    return el ? el.outerHTML : 'No element found';
                }""")
                
                dump_path = os.path.join(os.path.dirname(__file__), "dom_dump.txt")
                with open(dump_path, "w", encoding="utf-8") as f:
                    f.write(body_content)
                    
                results = {
                    "success": True,
                    "arrow_found": arrow_found,
                    "body_html_len": len(body_content),
                    "screenshot_saved": os.path.exists(diag_screenshot),
                    "dump_saved": os.path.exists(dump_path)
                }
            except Exception as inner_e:
                results = {"success": False, "error": str(inner_e)}
            finally:
                await context.close()
    except Exception as outer_e:
        results = {"success": False, "error": str(outer_e)}
    return results

@app.get("/player", response_class=HTMLResponse)
async def player_page(url: str, cookies: str = "", filename: str = "Video Player"):
    from urllib.parse import quote
    stream_url = f"/api/stream?url={quote(url)}&cookies={quote(cookies)}"
    download_url = f"/api/download?url={quote(url)}&filename={quote(filename)}&cookies={quote(cookies)}"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{filename}</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
        <style>
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            body {{
                font-family: 'Outfit', sans-serif;
                background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
                color: #f8fafc;
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                overflow-x: hidden;
                padding: 20px;
            }}
            .container {{
                width: 100%;
                max-width: 900px;
                background: rgba(30, 41, 59, 0.4);
                backdrop-filter: blur(16px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 24px;
                padding: 24px;
                box-shadow: 0 20px 40px rgba(0, 0, 0, 0.3);
                display: flex;
                flex-direction: column;
                gap: 20px;
                animation: fadeIn 0.6s cubic-bezier(0.16, 1, 0.3, 1);
            }}
            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
            .header {{
                text-align: center;
            }}
            h1 {{
                font-size: 1.8rem;
                font-weight: 800;
                background: linear-gradient(to right, #38bdf8, #818cf8);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                margin-bottom: 8px;
                word-break: break-all;
            }}
            p.subtitle {{
                font-size: 0.95rem;
                color: #94a3b8;
            }}
            .video-wrapper {{
                width: 100%;
                aspect-ratio: 16/9;
                border-radius: 16px;
                overflow: hidden;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
                background: #000;
                border: 1px solid rgba(255, 255, 255, 0.05);
            }}
            video {{
                width: 100%;
                height: 100%;
                object-fit: contain;
            }}
            .actions {{
                display: flex;
                gap: 16px;
                justify-content: center;
                flex-wrap: wrap;
            }}
            .btn {{
                display: inline-flex;
                align-items: center;
                gap: 8px;
                padding: 14px 28px;
                border-radius: 12px;
                font-weight: 600;
                text-decoration: none;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                cursor: pointer;
                font-size: 1rem;
            }}
            .btn-primary {{
                background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
                color: #fff;
                border: none;
                box-shadow: 0 4px 15px rgba(59, 130, 246, 0.4);
            }}
            .btn-primary:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(59, 130, 246, 0.6);
            }}
            .btn-secondary {{
                background: rgba(255, 255, 255, 0.1);
                color: #f8fafc;
                border: 1px solid rgba(255, 255, 255, 0.2);
            }}
            .btn-secondary:hover {{
                background: rgba(255, 255, 255, 0.2);
                transform: translateY(-2px);
            }}
            .footer {{
                margin-top: 30px;
                font-size: 0.8rem;
                color: #64748b;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>{filename}</h1>
                <p class="subtitle">Premium TeraBox Direct Player</p>
            </div>
            
            <div class="video-wrapper">
                <video controls autoplay playsinline preload="auto">
                    <source src="{stream_url}" type="video/mp4">
                    Your browser does not support the video tag.
                </video>
            </div>
            
            <div class="actions">
                <a href="{download_url}" class="btn btn-primary">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                    Download Video
                </a>
                <button onclick="window.location.reload();" class="btn btn-secondary">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"></path></svg>
                    Reload Stream
                </button>
            </div>
        </div>
        
        <div class="footer">
            Powered by TeraBot Premium Downloader Engine
        </div>
    </body>
    </html>
    """
    return html_content

@app.get("/api/stream")
async def stream_video(
    url: str | None = None,
    cookies: str | None = None,
    request: Request = None
):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    range_header = request.headers.get("range")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": unquote(cookies) if cookies else "",
        "Referer": "https://www.terabox.app/"
    }
    if range_header:
        headers["Range"] = range_header

    client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)
    try:
        response = await client.send(
            client.build_request("GET", url, headers=headers),
            stream=True
        )
        res_headers = {
            "Content-Type": response.headers.get("Content-Type", "video/mp4"),
            "Accept-Ranges": response.headers.get("Accept-Ranges", "bytes")
        }
        if response.headers.get("Content-Range"):
            res_headers["Content-Range"] = response.headers.get("Content-Range")
        if response.headers.get("Content-Length"):
            res_headers["Content-Length"] = response.headers.get("Content-Length")

        async def stream_generator():
            try:
                async for chunk in response.aiter_bytes(chunk_size=1024*128):
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        return StreamingResponse(
            stream_generator(),
            status_code=response.status_code,
            headers=res_headers
        )
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download")
async def download_file(
    url: str | None = None,
    filename: str | None = None,
    cookies: str | None = None,
    local_file: str | None = None
):
    if local_file:
        # Prevent path traversal attacks by getting just the basename
        safe_filename = os.path.basename(local_file)
        file_path = os.path.join("/tmp", safe_filename)
        if not os.path.exists(file_path):
            # Fallback to local directory
            fallback_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), safe_filename)
            if os.path.exists(fallback_path):
                file_path = fallback_path
            else:
                raise HTTPException(status_code=404, detail="File not found")
            
        # Set up a background task to delete the file after it is served
        from fastapi import BackgroundTasks
        background_tasks = BackgroundTasks()
        def delete_file(path: str):
            try:
                # Wait 5 seconds after serving to ensure release
                import time
                time.sleep(5)
                if os.path.exists(path):
                    os.remove(path)
                    print(f"Cleaned up served local file: {path}")
            except Exception as e:
                print(f"Error deleting served file: {e}")
                
        background_tasks.add_task(delete_file, file_path)
        return FileResponse(
            file_path,
            filename=filename or safe_filename,
            background=background_tasks
        )

    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Cookie": unquote(cookies) if cookies else "",
        "Referer": "https://www.terabox.app/"
    }

    async def stream_generator():
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("GET", url, headers=headers, follow_redirects=True) as response:
                async for chunk in response.aiter_bytes(chunk_size=1024*64):
                    yield chunk

    # Return stream
    return StreamingResponse(
        stream_generator(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename or "video.mp4"}"'}
    )

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
