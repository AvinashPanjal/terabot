import subprocess

direct_url = "https://www.terabox.app/share/streaming?uk=4400709822803&shareid=35814489121&type=M3U8_AUTO_360&fid=475826685734645&sign=414495d164953d1def4e5523be12e44f28cb80c4&timestamp=1779176493&jsToken=28AFFA03B711F3D30E8FE6B05B15EE4EC3A60F8320B22837952A784DFFC5844CFF57DD2ED1A0090EBB406A67BAC546BCA274880A04D613A1AF19DF0AAE271C34F920982C5A05707D8D10B7BB335A98046273FF62D9221D324F58466A34034156AE9BD4821C6E5FFF55F62149DC2C74CC3887AC9D3EF2762BA0CE2DD62E152AB6&esl=1&isplayer=1&ehps=1&clienttype=0&app_id=250528&web=1&channel=dubox"

cmd = [
    'ffmpeg', '-allowed_extensions', 'ALL', '-user_agent', 'Mozilla/5.0', '-headers', 'Referer: https://www.terabox.app/\r\n',
    '-i', direct_url, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', 'test_ffmpeg_out.mp4', '-y'
]

print("Running FFmpeg...")
process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

print("FFmpeg exited with code:", process.returncode)
print("------ STDERR ------")
print(process.stderr[-1000:])
