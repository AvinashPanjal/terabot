import asyncio
from playwright.async_api import async_playwright
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("Navigating...")
        await page.goto("https://terafileshare.com/s/1_jdGChVPUQmgxzGgEYx0zA", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        html = await page.content()
        print("Got HTML. Length:", len(html))
        
        links = await page.evaluate('''() => {
            return Array.from(document.querySelectorAll('a')).map(a => ({text: a.innerText, href: a.href, class: a.className}));
        }''')
        
        for l in links:
            if 'download' in l['text'].lower() or 'dl' in l['class'].lower() or 'down' in l['class'].lower():
                print("Potential DL Link:", l)

        await browser.close()

asyncio.run(test())
