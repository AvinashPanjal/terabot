import asyncio
import os
from playwright.async_api import async_playwright

async def dump_html():
    user_data_dir = os.path.join(os.getcwd(), "browser_session")
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        if len(context.pages) > 0:
            page = context.pages[0]
        else:
            page = await context.new_page()
            
        print("Navigating to link...")
        await page.goto("https://terafileshare.com/s/1_jdGChVPUQmgxzGgEYx0zA", wait_until="domcontentloaded", timeout=30000)
        
        await page.wait_for_timeout(5000)
        
        print("Taking screenshot...")
        await page.screenshot(path="auth_html_dump.png")
        
        html = await page.content()
        with open("auth_dump.html", "w", encoding="utf-8") as f:
            f.write(html)
            
        print("Saved auth_dump.html")
        await context.close()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(dump_html())
