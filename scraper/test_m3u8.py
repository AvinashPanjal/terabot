import asyncio
import httpx

async def test():
    async with httpx.AsyncClient(timeout=180.0) as client:
        print("Extracting URL and cookies...")
        res = await client.post('http://127.0.0.1:8000/api/extract', json={'url': 'https://terafileshare.com/s/1xNFXYDDnCGnHeT6hAx2SwA'})
        data = res.json()
        direct_url = data.get("directUrl")
        cookies = data.get("cookies", "")
        
        print("Downloading M3U8 playlist directly...")
        
        # Parse the raw cookie string into a dict, and only keep important ones
        cookie_dict = {}
        for c in cookies.split("; "):
            if "=" in c:
                k, v = c.split("=", 1)
                # Keep ndus (main auth), and any ndus-related or session-related cookies
                if k in ["ndus", "csrfToken", "browserid", "lang", "PANWEB"] or "ndus" in k:
                    cookie_dict[k] = v
                    
        filtered_cookie_string = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])
        print(f"Filtered cookies length: {len(filtered_cookie_string)}")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.terabox.app/",
            "Cookie": filtered_cookie_string
        }
        import subprocess
        print("Testing yt-dlp with filtered cookies...")
        process = await asyncio.create_subprocess_exec(
            'yt-dlp', direct_url, 
            '--add-header', 'Referer: https://www.terabox.app/', 
            '--add-header', f'Cookie: {filtered_cookie_string}', 
            '-o', 'test_dl_filtered.mp4',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        print("yt-dlp output:", stdout.decode()[-500:])
        if stderr:
            print("yt-dlp error:", stderr.decode())

if __name__ == "__main__":
    asyncio.run(test())
