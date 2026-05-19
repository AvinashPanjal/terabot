from TeraboxDL.TeraboxDL.teraboxdl import TeraboxDL
from playwright.sync_api import sync_playwright
import os

def test():
    print("Extracting ndus cookie...")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=os.path.join(os.getcwd(), 'browser_session'))
        cookies = ctx.cookies()
        ndus = next((c['value'] for c in cookies if c['name'] == 'ndus'), None)
        ctx.close()
    
    if not ndus:
        print("ndus cookie not found!")
        return
        
    print(f"Using ndus: {ndus[:10]}...")
    cookie_str = f"ndus={ndus}"
    
    dl = TeraboxDL(cookie_str)
    info = dl.get_file_info("https://terafileshare.com/s/1xNFXYDDnCGnHeT6hAx2SwA")
    print("File Info:", info)

if __name__ == "__main__":
    test()
