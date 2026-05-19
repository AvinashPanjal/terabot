import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        async def handle_request(route, request):
            url = request.url
            if "terafileshare" not in url and "google" not in url and "bytecdn" not in url:
                if request.resource_type in ["fetch", "xhr", "media"]:
                    print(f"[{request.resource_type}] {url[:150]}...")
            await route.continue_()
            
        await page.route("**/*", handle_request)
        print("Navigating to terafileshare.com...")
        await page.goto("https://terafileshare.com/s/1_jdGChVPUQmgxzGgEYx0zA", wait_until="networkidle")
        await page.wait_for_timeout(5000)
        await browser.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
