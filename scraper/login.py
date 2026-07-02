import asyncio
from playwright.async_api import async_playwright
import os
import re

async def login_to_terabox():
    print("Launching browser...")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    user_data_dir = os.path.join(script_dir, "browser_session")
    
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
            
        print("Browser closed! Retrieving cookies...")
        
        # Retrieve all cookies
        cookies = await browser.cookies()
        ndus_cookie = next((c for c in cookies if c["name"] == "ndus"), None)
        
        if ndus_cookie:
            ndus_value = ndus_cookie["value"]
            print("\n" + "="*60)
            print("🎉 SUCCESS! SUCCESSFULLY EXTRACTED YOUR COOKIE:")
            print(f"TERABOX_NDUS = {ndus_value}")
            print("="*60 + "\n")
            
            # Save to local .env file in parent directory if it exists
            env_path = os.path.join(os.path.dirname(script_dir), ".env")
            if not os.path.exists(env_path):
                env_path = os.path.join(script_dir, ".env") # Fallback to scraper dir
                
            try:
                if os.path.exists(env_path):
                    with open(env_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    if "TERABOX_NDUS=" in content:
                        new_content = re.sub(r'TERABOX_NDUS\s*=.*', f'TERABOX_NDUS={ndus_value}', content)
                    else:
                        new_content = content.rstrip() + f'\nTERABOX_NDUS={ndus_value}\n'
                        
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    print(f"✅ Automatically updated your local .env file ({env_path})!")
                else:
                    with open(env_path, "w", encoding="utf-8") as f:
                        f.write(f"TERABOX_NDUS={ndus_value}\n")
                    print(f"✅ Created a new local .env file with your cookie!")
            except Exception as e:
                print(f"⚠️ Could not auto-save to .env file: {e}")
                
            print("\n👉 COPY the TERABOX_NDUS value above and paste it into Render!")
        else:
            print("\n❌ Could not find the 'ndus' cookie. Make sure you logged in fully before closing the browser.\n")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(login_to_terabox())
