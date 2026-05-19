import httpx
import asyncio
import sys

async def test_apis():
    url = "https://terafileshare.com/s/1_jdGChVPUQmgxzGgEYx0zA"
    shorturl = url.split("/s/")[1]
    
    print(f"Testing shorturl: {shorturl}")
    
    apis = [
        f"https://terabox-dl.qtcloud.workers.dev/api/get-info?shorturl={shorturl}&pwd=",
        f"https://terabox-downloader-api.vercel.app/api?url={url}",
        f"https://terabox.hnn.workers.dev/api/get-info?shorturl={shorturl}&pwd="
    ]
    
    async with httpx.AsyncClient() as client:
        for api in apis:
            print(f"\nTrying API: {api}")
            try:
                res = await client.get(api, timeout=10)
                print(f"Status: {res.status_code}")
                print(f"Response: {res.text[:500]}")
            except Exception as e:
                print(f"Error: {e}")

if __name__ == "__main__":
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(test_apis())
