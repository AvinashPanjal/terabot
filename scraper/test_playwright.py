import asyncio
from playwright.async_api import async_playwright
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

async def test():
    direct_url = None
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        async def handle_request(route, request):
            nonlocal direct_url
            url = request.url
            if "google.com" in url or "doubleclick.net" in url or "analytics" in url:
                await route.continue_()
                return
            if "/share/download" in url or "/share/streaming" in url or ".mp4" in url:
                if "terabox" in url or "baidupcs" in url or "box.com" in url or "pstatp.com" in url or "/api/download" in url:
                    print(f"Intercepted real media: {url}")
                    if not direct_url:
                        direct_url = url
            await route.continue_()

        await page.route("**/*", handle_request)
        print("Navigating...")
        await page.goto("https://terafileshare.com/s/1_jdGChVPUQmgxzGgEYx0zA", wait_until="domcontentloaded", timeout=30000)
        print("Loaded dom. Waiting for network...")
        await page.wait_for_timeout(5000)

        # try to click play button if it exists
        try:
            play_btn = await page.wait_for_selector(".vjs-big-play-button", timeout=3000)
            if play_btn:
                print("Clicking play button...")
                await play_btn.click()
                await page.wait_for_timeout(3000)
        except Exception as e:
            print("No play button found")

        print("Final Direct URL:", direct_url)
        await browser.close()

asyncio.run(test())
