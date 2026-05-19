import httpx
import os
import json
from dotenv import load_dotenv

load_dotenv()
terabox_cookie = os.getenv("TERABOX_COOKIE")

url = "1_jdGChVPUQmgxzGgEYx0zA"

cookies = {
    "ndus": terabox_cookie
}

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.terabox.app/"
}

print("Testing shorturlinfo API...")
res = httpx.get(f"https://www.terabox.app/api/shorturlinfo?app_id=250528&web=1&channel=dubox&clienttype=0&shorturl={url}", cookies=cookies, headers=headers)
print("Status:", res.status_code)
print("Response:", res.text[:1000])

try:
    data = res.json()
    if "list" in data and len(data["list"]) > 0:
        dlink = data["list"][0].get("dlink")
        print("\nFound dlink:", dlink)
        
        # Test downloading the dlink
        if dlink:
            print("\nTesting dlink accessibility...")
            dlink_res = httpx.get(dlink, headers=headers, cookies=cookies, follow_redirects=False)
            print("Dlink Status:", dlink_res.status_code)
            print("Dlink Headers:", dlink_res.headers)
            if dlink_res.status_code in [302, 301]:
                print("Redirects to:", dlink_res.headers.get("Location"))
except Exception as e:
    print("Error parsing JSON:", e)
