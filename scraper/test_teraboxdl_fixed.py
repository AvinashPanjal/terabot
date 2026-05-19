import requests
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright
import os

def _find_between(s: str, start: str, end: str) -> str:
    start_index = s.find(start) + len(start)
    end_index = s.find(end, start_index)
    if start_index == -1 or end_index == -1:
        return ""
    return s[start_index:end_index]

def test():
    print("Fetching cookies from API...")
    res_ext = requests.post('http://127.0.0.1:8000/api/extract', json={'url': 'https://terafileshare.com/s/1xNFXYDDnCGnHeT6hAx2SwA'}, timeout=60)
    data_ext = res_ext.json()
    all_cookies = data_ext.get("cookies", "")
    
    # Extract only ndus and csrfToken to avoid 400 Bad Request
    allowed_cookies = ['ndus', 'csrfToken']
    cookie_str = "; ".join([c for c in all_cookies.split("; ") if any(c.startswith(a + "=") for a in allowed_cookies)])
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36",
        "Cookie": cookie_str
    }
    
    link = "https://www.terabox.app/sharing/link?surl=xNFXYDDnCGnHeT6hAx2SwA"
    print("Fetching", link)
    
    temp_req = requests.get(link, headers=headers, timeout=30)
    parsed_url = urlparse(temp_req.url)
    query_params = parse_qs(parsed_url.query)
    
    surl = query_params.get("surl", [""])[0]
    respo = temp_req.text
    
    js_token = _find_between(respo, 'fn%28%22', '%22%29')
    logid = _find_between(respo, 'dp-logid=', '&')
    
    print("js_token:", js_token[:10])
    print("logid:", logid)
    print("surl:", surl)
    
    params = {
        "app_id": "250528",
        "web": "1",
        "channel": "dubox",
        "clienttype": "0",
        "jsToken": js_token,
        "dp-logid": logid,
        "page": "1",
        "num": "20",
        "by": "name",
        "order": "asc",
        "site_referer": temp_req.url,
        "shorturl": surl,
        "root": "1",
    }
    
    req2 = requests.get("https://www.terabox.app/share/list", headers=headers, params=params, timeout=30)
    response_data2 = req2.json()
    print("Share list response keys:", response_data2.keys())
    if "list" in response_data2 and response_data2["list"]:
        file_info = response_data2["list"][0]
        print("Filename:", file_info.get("server_filename"))
        print("dlink length:", len(file_info.get("dlink", "")))
        print("dlink:", file_info.get("dlink", "")[:100])
    else:
        print("Failed to get file list:", response_data2)

if __name__ == "__main__":
    test()
