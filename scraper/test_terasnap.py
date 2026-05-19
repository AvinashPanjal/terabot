import httpx
from playwright.sync_api import sync_playwright
import os
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        print("Extracting ndus cookie via API...")
        res_ext = await client.post('http://127.0.0.1:8000/api/extract', json={'url': 'https://terafileshare.com/s/1xNFXYDDnCGnHeT6hAx2SwA'}, timeout=60)
        data_ext = res_ext.json()
        cookies = data_ext.get("cookies", "")
        
        ndus = ""
        for c in cookies.split("; "):
            if c.startswith("ndus="):
                ndus = c.split("=")[1]
                break
        
        if not ndus:
            print("ndus cookie not found!")
            return
            
        print(f"ndus: {ndus[:10]}...")
        payload = {
            "link": "https://terafileshare.com/s/1xNFXYDDnCGnHeT6hAx2SwA",
            "cookies": f"ndus={ndus}"
        }
        
        print("Querying terasnap API...")
        res = await client.post("https://terasnap.netlify.app/api/download", json=payload, timeout=30)
        print("Status:", res.status_code)
        try:
            data = res.json()
            print("Direct link length:", len(data.get("download_link", "")))
            print(data.get("download_link", "")[:100])
        except Exception as e:
            print("Error:", e, res.text)

if __name__ == "__main__":
    asyncio.run(test())
