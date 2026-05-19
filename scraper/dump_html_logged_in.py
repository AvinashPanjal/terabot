from playwright.sync_api import sync_playwright
import os

def run():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=os.path.join(os.getcwd(), 'browser_session'), 
            headless=True,
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = ctx.pages[0] if len(ctx.pages) > 0 else ctx.new_page()
        
        def handle_response(response):
            url = response.url
            if "share/list" in url:
                try:
                    data = response.json()
                    print("Found /share/list! Keys:", data.keys())
                    import json
                    with open("share_list_response.json", "w", encoding="utf-8") as sj:
                        json.dump(data, sj, indent=4)
                    print("Saved share_list_response.json!")
                except Exception as e:
                    print("Failed to save share/list JSON:", e)
            if any(ext in url for ext in [".js", ".css", ".png", ".jpg", ".svg", ".woff", "analytics", "reporterror", "logid"]):
                return
            print(f"[{response.status}] {response.request.method} {url}")
            try:
                # print body if it's JSON or transfer/share related
                if "transfer" in url or "share" in url or "api" in url:
                    print("  -> Body:", response.text()[:200])
            except Exception:
                pass
        
        page.on("response", handle_response)
        
        print("Navigating to terafileshare link...")
        page.goto("https://terafileshare.com/s/1xNFXYDDnCGnHeT6hAx2SwA")
        
        print("Waiting 10 seconds for page to render...")
        page.wait_for_timeout(10000)
        
        print("Saving HTML...")
        with open("terabox_rendered.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        
        print("Clicking Save button...")
        try:
            page.locator("button.save-btn").first.click(timeout=5000)
            print("Clicked button.save-btn!")
        except Exception as e:
            print("Could not click button.save-btn:", e)
            try:
                page.locator("button.save-btn").first.click(timeout=5000, force=True)
                print("Clicked button.save-btn with force=True!")
            except Exception as e2:
                print("Could not click button.save-btn even with force=True:", e2)
        print("Waiting 10 seconds to see intercepted requests...")
        page.wait_for_timeout(10000)
        ctx.close()

run()
