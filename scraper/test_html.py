import requests
from playwright.sync_api import sync_playwright
import os

def test():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=os.path.join(os.getcwd(), 'browser_session'))
        cookies = ctx.cookies()
        ndus = next((c['value'] for c in cookies if c['name'] == 'ndus'), None)
        ctx.close()
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Cookie": f"ndus={ndus}"
    }
    
    url = "https://terafileshare.com/s/1xNFXYDDnCGnHeT6hAx2SwA"
    print("Fetching", url)
    r = requests.get(url, headers=headers)
    print("Length:", len(r.text))
    
    # Save the HTML for inspection
    with open("terabox_response.html", "w", encoding="utf-8") as f:
        f.write(r.text)
        
    print("bdstoken in html:", "bdstoken" in r.text)
    print("jsToken in html:", "jsToken" in r.text)

if __name__ == "__main__":
    test()
