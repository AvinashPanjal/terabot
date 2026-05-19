import asyncio
from playwright.async_api import async_playwright
import json

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        print("Navigating...")
        await page.goto("https://terafileshare.com/s/1_jdGChVPUQmgxzGgEYx0zA", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)
        
        # Dump window properties
        res = await page.evaluate('''() => {
            let links = [];
            let scripts = document.querySelectorAll('script');
            scripts.forEach(s => {
                if (s.innerText.includes('http')) {
                    links.push(s.innerText.substring(0, 500));
                }
            });
            return {
                html: document.body.innerHTML.substring(0, 1000),
                scripts: links
            };
        }''')
        
        with open("dump.json", "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
            
        print("Dumped to dump.json")
        await browser.close()

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(main())
