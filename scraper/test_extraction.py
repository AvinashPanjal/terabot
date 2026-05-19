import asyncio
import httpx
import subprocess

async def test():
    async with httpx.AsyncClient(timeout=180.0) as client:
        print("Sending request to extraction API...")
        res = await client.post('http://127.0.0.1:8000/api/extract', json={'url': 'https://terafileshare.com/s/1xNFXYDDnCGnHeT6hAx2SwA'})
        print("Status Code:", res.status_code)
        data = res.json()
        print("Direct URL:", data.get("directUrl"))
        
        cookies = data.get("cookies", "")
        print(f"Extracted cookies length: {len(cookies)}")
        
        # Test yt-dlp
        print("Testing yt-dlp...")
        process = await asyncio.create_subprocess_exec(
            'yt-dlp', data.get("directUrl"), 
            '--add-header', 'Referer: https://www.terabox.app/', 
            '--add-header', f'Cookie: {cookies}', 
            '-o', 'test_download.mp4',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        print("yt-dlp output:", stdout.decode()[-500:])
        if stderr:
            print("yt-dlp error:", stderr.decode())

if __name__ == "__main__":
    asyncio.run(test())
