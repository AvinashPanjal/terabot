import asyncio
from curl_cffi.requests import AsyncSession

async def test():
    async with AsyncSession(impersonate="chrome110") as s:
        try:
            r = await s.get("https://terabox.com/s/1_jdGChVPUQmgxzGgEYx0zA")
            print("Status:", r.status_code)
            print("Response:", r.text[:500])
        except Exception as e:
            print("Error:", e)

asyncio.run(test())
