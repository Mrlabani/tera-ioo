import os
import json
import aiohttp
import asyncio
from flask import Flask, request, jsonify
from urllib.parse import urlparse
import re

app = Flask(__name__)

SUPPORTED_DOMAINS = [
    "terabox.com", "1024terabox.com", "teraboxapp.com",
    "terafileshare.com", "teraboxlink.com", "terasharelink.com",
    "www.1024tera.com", "www.terabox.com", "terabox.download"
]

def load_cookies_txt(path="cookie.txt"):
    cookies = {}
    if not os.path.exists(path):
        return None
    with open(path, 'r') as f:
        for line in f:
            if line.startswith('#') or not line.strip():
                continue
            parts = line.strip().split('\t')
            if len(parts) >= 7:
                name = parts[5]
                value = parts[6]
                cookies[name] = value
    return cookies

def format_size(bytes):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024
    return f"{bytes:.2f} PB"

def generate_thumbnails(fs_id):
    return {
        "140x90": f"https://data.1024tera.com/thumbnail/{fs_id}?size=c140_u90&quality=100&ft=video",
        "360x270": f"https://data.1024tera.com/thumbnail/{fs_id}?size=c360_u270&quality=100&ft=video",
        "60x60": f"https://data.1024tera.com/thumbnail/{fs_id}?size=c60_u60&quality=100&ft=video",
        "850x580": f"https://data.1024tera.com/thumbnail/{fs_id}?size=c850_u580&quality=100&ft=video"
    }

async def extract_uk_shareid(session, url):
    headers = {"User-Agent": "Mozilla/5.0"}
    async with session.get(url, headers=headers) as resp:
        html = await resp.text()
        try:
            if 'window.globalData =' in html:
                json_str = html.split('window.globalData =')[-1].split(';</script>')[0].strip()
                data = json.loads(json_str)
                return str(data["share"]["uk"]), str(data["share"]["shareid"])
            uk_match = re.search(r'"uk":\s*(\d+)', html)
            sid_match = re.search(r'"shareid":\s*(\d+)', html)
            if uk_match and sid_match:
                return uk_match.group(1), sid_match.group(1)
        except Exception:
            pass
        return None, None

async def get_folder_files(session, shareid, uk, url):
    api_url = "https://www.terabox.com/share/list"
    payload = {
        "shorturl": "",
        "shareid": shareid,
        "uk": uk,
        "fid_list": "all",
        "primaryid": shareid,
        "is_rename": 0,
        "channel": "android_12",
        "web": 1
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": url,
        "Origin": "https://www.terabox.com",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    async with session.post(api_url, data=payload, headers=headers) as resp:
        return await resp.json()

async def get_download_link(session, shareid, fs_id, uk):
    dl_api = "https://www.terabox.com/api/sharedownload"
    payload = {
        "product": "share",
        "nozip": 0,
        "fid_list": f"[{fs_id}]",
        "primaryid": shareid,
        "uk": uk,
        "channel": "android_12",
        "web": 1,
        "clienttype": 0
    }
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.terabox.com/",
        "Origin": "https://www.terabox.com",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    async with session.post(dl_api, data=payload, headers=headers) as resp:
        try:
            data = await resp.json()
            dlink = data['list'][0]['dlink']
            fast = dlink.replace("d.1024tera.com", "d8.freeterabox.com")
            return dlink, fast
        except:
            return None, None

@app.route("/api", methods=["GET"])
def api():
    url = request.args.get("extract")
    if not url:
        return jsonify({"error": "Missing ?extract=<terabox_url>"}), 400

    parsed = urlparse(url)
    if parsed.netloc not in SUPPORTED_DOMAINS:
        return jsonify({"error": "Unsupported domain", "supported": SUPPORTED_DOMAINS}), 400

    cookies = load_cookies_txt("cookie.txt")
    if not cookies:
        return jsonify({"error": "cookie.txt is missing or invalid"}), 500

    async def process():
        async with aiohttp.ClientSession(cookies=cookies) as session:
            uk, shareid = await extract_uk_shareid(session, url)
            if not uk or not shareid:
                return {"error": "Unable to extract uk/shareid from URL"}

            folder_data = await get_folder_files(session, shareid, uk, url)
            if folder_data.get("errno") != 0:
                return {"error": "TeraBox API failed", "raw": folder_data}

            files = []
            for item in folder_data.get("list", []):
                if item.get("isdir") == 0:
                    title = item.get("server_filename")
                    size = format_size(item.get("size"))
                    fs_id = item.get("fs_id")
                    dlink, fast = await get_download_link(session, shareid, fs_id, uk)
                    thumbs = generate_thumbnails(fs_id)
                    files.append({
                        "📂 Title": title,
                        "📏 Size": size,
                        "🔻 Direct Download Link": dlink,
                        "🚀 Fast Download Link": fast,
                        "🖼️ Thumbnails": thumbs
                    })

            return {
                "🔗 ShortLink": url,
                "📄 Extracted Info": files,
                "✅ Status": "Success",
                "📊 Item Count": len(files),
                "developer": "https://t.me/l_abani"
            }

    try:
        result = asyncio.run(process())
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
          
