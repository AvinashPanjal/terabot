import asyncio
import os
from playwright.async_api import async_playwright

async def test_page():
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
        await page.screenshot(path="auth_test_screenshot.png")
        
        html = await page.content()
        print("Page HTML contains video tag:", "<video" in html)
        print("Page HTML contains M3U8 string:", "m3u8" in html.lower() or "m3u8" in html.upper())
        
        # Try finding the video element and playing it
        try:
            res = await page.evaluate("() => { const v = document.querySelector('video'); if(v){ v.play(); return 'Played'; } return 'No video element'; }")
            print("Video play result:", res)
        except Exception as e:
            print("Error playing:", e)
            
        # Try looking for download button
        try:
            dl_btn = await page.query_selector('a.download-btn, a[title="Download"], button[title="Download"], .download-btn')
            print("Download button found:", dl_btn is not None)
            if dl_btn:
                href = await dl_btn.get_attribute("href")
                print("Download href:", href)
        except Exception as e:
            print("Error finding download button:", e)

        await context.close()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(test_page())
