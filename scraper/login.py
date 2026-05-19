import asyncio
from playwright.async_api import async_playwright
import os

async def login_to_terabox():
    print("Launching browser...")
    user_data_dir = os.path.join(os.getcwd(), "browser_session")
    
    async with async_playwright() as p:
        # Launch browser in non-headless mode so you can see it and log in
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        page = await browser.new_page()
        print("Navigating to Terabox...")
        await page.goto("https://www.terabox.app/")
        
        print("\n=======================================================")
        print("1. Please log in to your TeraBox account in the browser.")
        print("2. Once you are successfully logged in and see your dashboard,")
        print("   close the browser window manually.")
        print("=======================================================\n")
        
        # Wait until the user closes the browser
        try:
            await page.wait_for_event("close", timeout=0)
        except Exception:
            pass
            
        print("Browser closed! Your session has been saved.")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(login_to_terabox())
