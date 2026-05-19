import httpx
import subprocess
import time

print("Fetching direct URL from local API...")
res = httpx.post("http://127.0.0.1:8000/api/extract", json={"url": "https://terafileshare.com/s/1_jdGChVPUQmgxzGgEYx0zA"}, timeout=60.0)
if res.status_code != 200:
    print(f"Extraction failed: {res.text}")
    exit(1)

data = res.json()
direct_url = data.get("directUrl")
print(f"Direct URL: {direct_url[:100]}...")

cmd = [
    'ffmpeg', '-user_agent', 'Mozilla/5.0', '-headers', 'Referer: https://www.terabox.app/\r\n',
    '-i', direct_url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', 'test_ffmpeg_out.mp4', '-y'
]

print("Running FFmpeg...")
process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

print("FFmpeg exited with code:", process.returncode)
print("------ STDERR ------")
print(process.stderr[-1000:])
