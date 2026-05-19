import sys
import asyncio

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from playwright.async_api import async_playwright
import uvicorn
import os
import re
import httpx
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Terabox Extraction Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

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

cookie_index = 0

async def get_all_cookies() -> list:
    pool = list(NDUS_POOL)
    # Fallback to local Playwright browser cookies if pool is empty
    if not pool:
        pw_cookies = await get_browser_cookies()
        pw_ndus = pw_cookies.get("ndus")
        if pw_ndus:
            pool.append(pw_ndus)
    return pool

async def get_next_cookie() -> str:
    global cookie_index
    pool = await get_all_cookies()
    if not pool:
        return None
    cookie = pool[cookie_index % len(pool)]
    cookie_index += 1
    return cookie

async def keep_alive_task():
    # Wait a few seconds for server startup
    await asyncio.sleep(5)
    while True:
        pool = await get_all_cookies()
        if not pool:
            print("Keep-alive check: No cookies configured in the pool.")
        else:
            print(f"Keep-alive check: Verifying {len(pool)} cookies in the pool...")
            for i, ndus in enumerate(pool):
                try:
                    headers = {
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Cookie": f"ndus={ndus}",
                        "Referer": "https://www.terabox.app/"
                    }
                    async with httpx.AsyncClient(timeout=15.0) as client:
                        # Request the main page to keep the session active
                        res = await client.get("https://www.terabox.app/main", headers=headers)
                        if res.status_code == 200 and "login" not in str(res.url):
                            print(f"Cookie #{i+1} ({ndus[:8]}...): Active & Healthy")
                        else:
                            print(f"Cookie #{i+1} ({ndus[:8]}...): Expired or Invalid! (Status: {res.status_code}, URL: {res.url})")
                except Exception as e:
                    print(f"Cookie #{i+1} ({ndus[:8]}...): Error during keep-alive: {e}")
        # Sleep for 1 hour
        await asyncio.sleep(3600)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(keep_alive_task())

@app.post("/api/extract")
async def extract_url(req: ExtractRequest):
    url = req.url
    req_ndus = req.ndus
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    print(f"Extraction request for link: {url}")
    
    # 1. TRY THE CLOUDFLARE WORKER PROXY FIRST (FAST & BYPASSES PREVIEW LIMIT/CAPTCHA)
    try:
        surl = extract_surl(url)
        if not surl:
            print("Could not extract surl, skipping proxy check.")
        else:
            print(f"Extracted surl: {surl}. Fetching cookies...")
            if req_ndus:
                cookies_dict = {"ndus": req_ndus}
                ndus = req_ndus
            else:
                ndus = await get_next_cookie()
                cookies_dict = {"ndus": ndus} if ndus else {}
                
            if not ndus:
                print("ndus cookie not found. Cannot use proxy.")
            else:
                proxy_url = "https://tbx-proxy.shakir-ansarii075.workers.dev/"
                params = {
                    "mode": "resolve",
                    "surl": surl,
                    "raw": "1"
                }
                headers_proxy = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
                }
                print("Querying tbx-proxy Cloudflare Worker...")
                async with httpx.AsyncClient(timeout=30.0) as client:
                    res = await client.get(proxy_url, params=params, headers=headers_proxy, cookies={"ndus": ndus})
                    
                if res.status_code == 200:
                    data = res.json()
                    dlink = None
                    filename = "video.mp4"
                    
                    if "upstream" in data and "list" in data["upstream"] and data["upstream"]["list"]:
                        dlink = data["upstream"]["list"][0].get("dlink")
                        filename = data["upstream"]["list"][0].get("server_filename", "video.mp4")
                    elif "data" in data and "list" in data["data"] and data["data"]["list"]:
                        dlink = data["data"]["list"][0].get("dlink")
                        filename = data["data"]["list"][0].get("server_filename", "video.mp4")
                        
                    if dlink:
                        print(f"Proxy successfully resolved dlink for {filename}!")
                        cookie_string = "; ".join([f"{k}={v}" for k, v in cookies_dict.items()])
                        return {
                            "success": True,
                            "directUrl": dlink,
                            "filename": filename,
                            "cookies": cookie_string
                        }
                    else:
                        print("Proxy did not return a dlink. Response data:", data)
                else:
                    print(f"Proxy failed with status code {res.status_code}: {res.text}")
    except Exception as e:
        print(f"Error during proxy extraction attempt: {e}")
        
    print("Proxy extraction failed or skipped. Falling back to Playwright browser automation...")

    # 2. FALLBACK TO PLAYWRIGHT BROWSER AUTOMATION
    direct_url = None
    filename = "video.mp4"
    cookie_string = ""

    try:
        async with async_playwright() as p:
            user_data_dir = os.path.join(os.path.dirname(__file__), "browser_session")
            
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=True,
                args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"],
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            if req_ndus:
                # Inject the custom user cookie into the browser session
                domains = [".terabox.app", ".teraboxapp.com", ".1024tera.com", ".terafileshare.com", ".nephobox.com"]
                await context.add_cookies([{
                    "name": "ndus",
                    "value": req_ndus,
                    "domain": d,
                    "path": "/"
                } for d in domains])
            
            if len(context.pages) > 0:
                page = context.pages[0]
            else:
                page = await context.new_page()

            async def handle_request(route, request):
                nonlocal direct_url
                req_url = request.url
                if "google.com" in req_url or "doubleclick.net" in req_url or "analytics" in req_url:
                    await route.continue_()
                    return
                
                if request.resource_type in ["image", "stylesheet", "font", "script"]:
                    await route.continue_()
                    return

                if ".ts" in req_url or "_ts/" in req_url:
                    await route.continue_()
                    return

                if "SUBTITLE" in req_url or "subtitle" in req_url or ".srt" in req_url:
                    await route.continue_()
                    return

                if "api/download" in req_url or "type=D" in req_url or ".m3u8" in req_url or "type=M3U8" in req_url or ("freeterabox.com" in req_url and "video" in req_url):
                    if "terabox" in req_url or "baidupcs" in req_url or "freeterabox" in req_url:
                        if "thumbnail" not in req_url and "favicon" not in req_url:
                            if not direct_url:
                                direct_url = req_url
                await route.continue_()

            await page.route("**/*", handle_request)

            print(f"Navigating to {url} ...")
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                print("Page loaded.")
            except Exception as e:
                print(f"Playwright error during goto: {e}")

            print("Waiting for direct_url interception...")
            for _ in range(15):
                if direct_url:
                    break
                await page.wait_for_timeout(1000)
                
            if not direct_url:
                print("No direct_url yet. Checking if we are in file list view...")
                try:
                    file_row = await page.wait_for_selector('.file-name, .file-list-row, .wp-s-core-pan-file-list-item, .wp-s-pan-file-list-row', timeout=20000)
                    if file_row:
                        print("Found file list row. Clicking it to open video player...")
                        await file_row.click()
                        await page.wait_for_timeout(3000)
                except Exception:
                    print("Did not find file list row.")

            if not direct_url:
                print("Checking for video element...")
                try:
                    await page.wait_for_selector("video", timeout=30000)
                    print("Video element found! Forcing play...")
                    await page.evaluate("() => { const v = document.querySelector('video'); if(v){ v.muted = true; v.play(); } }")
                    
                    async def keep_playing():
                        for _ in range(5):
                            await asyncio.sleep(2)
                            try:
                                await page.evaluate("() => { const v = document.querySelector('video'); if(v && v.paused){ v.play(); } }")
                            except:
                                pass
                    asyncio.create_task(keep_playing())
                    
                    print("Waiting 10s for stream to load...")
                    for _ in range(10):
                        if direct_url:
                            print("Stream loaded!")
                            break
                        await page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"Video element error or timeout: {e}")

            if not direct_url:
                print("Checking for Download button as fallback...")
                try:
                    dl_btn = await page.wait_for_selector('a.download-btn, a[title="Download"], button[title="Download"], .download-btn', timeout=5000)
                    if dl_btn:
                        print("Found download button! Clicking...")
                        try:
                            async with page.expect_download(timeout=10000) as download_info:
                                await dl_btn.click()
                            download = await download_info.value
                            direct_url = download.url
                        except Exception:
                            href = await dl_btn.get_attribute("href")
                            if href and href != "javascript:void(0);":
                                direct_url = href
                            else:
                                await dl_btn.click()
                                await page.wait_for_timeout(3000)
                except Exception:
                    print("Download button not found.")
            
            if direct_url and direct_url.startswith("/"):
                direct_url = "https://www.1024tera.com" + direct_url
                
            cookies = await context.cookies()
            cookie_string = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

            await context.close()
            
    except Exception as e:
        print(f"Playwright error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if not direct_url:
        raise HTTPException(status_code=404, detail="Could not extract direct download URL from TeraBox link.")

    return {
        "success": True,
        "directUrl": direct_url,
        "filename": filename,
        "cookies": cookie_string
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
