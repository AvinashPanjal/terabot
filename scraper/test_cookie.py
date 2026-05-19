import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright

load_dotenv()
terabox_cookie = os.getenv("TERABOX_COOKIE")

async def test_cookie():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        
        if terabox_cookie:
            print("Injecting cookie...")
            cookies = []
            domains = [".terabox.app", ".terafileshare.com", ".1024tera.com", ".terabox.com", ".freeterabox.com"]
            for d in domains:
                cookies.append({"name": "ndus", "value": terabox_cookie, "domain": d, "path": "/"})
            await context.add_cookies(cookies)
            
        page = await context.new_page()
        print("Navigating to video...")
        await page.goto("https://terafileshare.com/s/1_jdGChVPUQmgxzGgEYx0zA", wait_until="domcontentloaded")
        
        print("Waiting 10 seconds...")
        await page.wait_for_timeout(10000)
        
        # Check if we are logged in by looking for a profile element or login button
        login_btn = await page.evaluate("document.body.innerHTML.includes('Log in') || document.body.innerHTML.includes('Login') || document.body.innerHTML.includes('sign up')")
        print("Login button found (meaning we are NOT logged in):", login_btn)
        
        await page.screenshot(path="cookie_test_screenshot.png")
        print("Screenshot saved to cookie_test_screenshot.png")
        
        await browser.close()

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(test_cookie())
