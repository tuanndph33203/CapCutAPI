import os
import subprocess
import time
import requests
import shutil
from typing import Optional
from requests.exceptions import RequestException, Timeout
from urllib.parse import urlparse, unquote

def download_video(video_url, draft_name, material_name):
    """
    Download video to specified directory
    :param video_url: Video URL
    :param draft_name: Draft name
    :param material_name: Material name
    :return: Local video path
    """
    # Ensure directory exists
    video_dir = f"{draft_name}/assets/video"
    os.makedirs(video_dir, exist_ok=True)
    
    # Generate local filename
    local_path = f"{video_dir}/{material_name}"
    
    # Check if file already exists
    if os.path.exists(local_path):
        print(f"Video file already exists: {local_path}")
        return local_path
    
    try:
        # Use ffmpeg to download video
        command = [
            'ffmpeg',
            '-i', video_url,
            '-c', 'copy',  # Direct copy, no re-encoding
            local_path
        ]
        subprocess.run(command, check=True, capture_output=True)
        return local_path
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to download video: {e.stderr.decode('utf-8')}")

def download_image(image_url, draft_name, material_name):
    """
    Download image to specified directory, and convert to PNG format
    :param image_url: Image URL
    :param draft_name: Draft name
    :param material_name: Material name
    :return: Local image path
    """
    # Ensure directory exists
    image_dir = f"{draft_name}/assets/image"
    os.makedirs(image_dir, exist_ok=True)
    
    # Uniformly use png format
    local_path = f"{image_dir}/{material_name}"
    
    # Check if file already exists
    if os.path.exists(local_path):
        print(f"Image file already exists: {local_path}")
        return local_path
    
    try:
        # Use ffmpeg to download and convert image to PNG format
        command = [
            'ffmpeg',
            '-i', image_url,
            '-vf', 'format=rgba',  # Convert to RGBA format to support transparency
            '-frames:v', '1',      # Ensure only one frame is processed
            '-y',                  # Overwrite existing files
            local_path
        ]
        subprocess.run(command, check=True, capture_output=True)
        return local_path
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to download image: {e.stderr.decode('utf-8')}")

def download_audio(audio_url, draft_name, material_name):
    """
    Download audio and transcode to MP3 format to specified directory
    :param audio_url: Audio URL
    :param draft_name: Draft name
    :param material_name: Material name
    :return: Local audio path
    """
    # Ensure directory exists
    audio_dir = f"{draft_name}/assets/audio"
    os.makedirs(audio_dir, exist_ok=True)
    
    # Generate local filename (keep .mp3 extension)
    local_path = f"{audio_dir}/{material_name}"
    
    # Check if file already exists
    if os.path.exists(local_path):
        print(f"Audio file already exists: {local_path}")
        return local_path
    
    try:
        # Use ffmpeg to download and transcode to MP3 (key modification: specify MP3 encoder)
        command = [
            'ffmpeg',
            '-i', audio_url,          # Input URL
            '-c:a', 'libmp3lame',     # Force encode audio stream to MP3
            '-q:a', '2',              # Set audio quality (0-9, 0 is best, 2 balances quality and file size)
            '-y',                     # Overwrite existing files (optional)
            local_path                # Output path
        ]
        subprocess.run(command, check=True, capture_output=True, text=True)
        return local_path
    except subprocess.CalledProcessError as e:
        raise Exception(f"Failed to download audio:\n{e.stderr}")

def download_file(url:str, local_filename, max_retries=3, timeout=180):
    # 检查是否是本地文件路径
    if os.path.exists(url) and os.path.isfile(url):
        # 是本地文件，直接复制
        directory = os.path.dirname(local_filename)
        
        # 创建目标目录（如果不存在）
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)
            print(f"Created directory: {directory}")
        
        print(f"Copying local file: {url} to {local_filename}")
        start_time = time.time()
        
        # 复制文件
        shutil.copy2(url, local_filename)
        
        print(f"Copy completed in {time.time()-start_time:.2f} seconds")
        print(f"File saved as: {os.path.abspath(local_filename)}")
        return True
    
    # 原有的下载逻辑
    # Extract directory part
    directory = os.path.dirname(local_filename)

    retries = 0
    while retries < max_retries:
        try:
            if retries > 0:
                wait_time = 2 ** retries  # Exponential backoff strategy
                print(f"Retrying in {wait_time} seconds... (Attempt {retries+1}/{max_retries})")
                time.sleep(wait_time)
            
            print(f"Downloading file: {local_filename}")
            start_time = time.time()
            
            # Create directory (if it doesn't exist)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                print(f"Created directory: {directory}")

            with requests.get(url, stream=True, timeout=timeout) as response:
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                block_size = 1024
                
                with open(local_filename, 'wb') as file:
                    bytes_written = 0
                    for chunk in response.iter_content(block_size):
                        if chunk:
                            file.write(chunk)
                            bytes_written += len(chunk)
                            
                            if total_size > 0:
                                progress = bytes_written / total_size * 100
                                # For frequently updated progress, consider using logger.debug or more granular control to avoid large log files
                                # Or only output progress to console, not write to file
                                print(f"\r[PROGRESS] {progress:.2f}% ({bytes_written/1024:.2f}KB/{total_size/1024:.2f}KB)", end='')
                                pass # Avoid printing too much progress information in log files
                
                if total_size > 0:
                    # print() # Original newline
                    pass
                print(f"Download completed in {time.time()-start_time:.2f} seconds")
                print(f"File saved as: {os.path.abspath(local_filename)}")
                return True
                
        except Timeout:
            print(f"Download timed out after {timeout} seconds")
        except RequestException as e:
            print(f"Request failed: {e}")
        except Exception as e:
            print(f"Unexpected error during download: {e}")
        
        retries += 1
    
    print(f"Download failed after {max_retries} attempts for URL: {url}")
    return False


import re
import urllib.parse


def clean_and_resolve_url(raw_text: str) -> str:
    """
    Extract embedded URL from raw share text (e.g. Douyin / TikTok / CapCut share strings),
    expand short links (v.douyin.com, vt.tiktok.com), and normalize video modal URLs.
    """
    if not raw_text:
        return raw_text

    # 1. Extract http:// or https:// URL from text
    match = re.search(r'https?://[^\s\u4e00-\u9fff]+', raw_text)
    if not match:
        match = re.search(r'https?://[^\s]+', raw_text)

    if not match:
        return raw_text.strip()

    url = match.group(0).rstrip('!,.?()；;')

    # 2. Douyin link normalization
    if "douyin.com" in url:
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        video_id = query.get('modal_id', [None])[0] or query.get('vid', [None])[0]
        if video_id:
            return f"https://www.douyin.com/video/{video_id}"

        if "v.douyin.com" in url:
            try:
                resp = requests.get(url, allow_redirects=True, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }, timeout=5)
                final_url = resp.url
                video_match = re.search(r'/video/(\d+)', final_url)
                if video_match:
                    return f"https://www.douyin.com/video/{video_match.group(1)}"
                return final_url
            except Exception as e:
                print(f"[clean_and_resolve_url] Douyin redirect expand error: {e}")

    # 3. TikTok short link normalization
    elif "vt.tiktok.com" in url:
        try:
            resp = requests.get(url, allow_redirects=True, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }, timeout=5)
            return resp.url
        except Exception as e:
            print(f"[clean_and_resolve_url] TikTok redirect expand error: {e}")

    return url


def download_douyin_no_watermark(raw_text: str, output_dir: str = "downloads") -> dict:
    """
    Direct no-watermark Douyin downloader bypassing cookie & login requirements.
    Uses dynamic ttwid session registration & Douyin aweme feed / detail API.
    Creates a dedicated folder per video, downloads both video and cover/banner image.
    """
    import json
    import requests
    os.makedirs(output_dir, exist_ok=True)

    clean_url = clean_and_resolve_url(raw_text)
    video_id_match = re.search(r'(\d{15,22})', clean_url)
    if not video_id_match and ("v.douyin.com" in raw_text or "douyin.com" in raw_text):
        try:
            match_url = re.search(r'https?://[^\s]+', raw_text)
            if match_url:
                resp = requests.get(match_url.group(0), headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                }, allow_redirects=True, timeout=5)
                video_id_match = re.search(r'(\d{15,22})', resp.url)
        except Exception:
            pass

    if not video_id_match:
        return {"success": False, "error": "Could not extract Douyin video ID", "file_path": None, "cover_path": None}

    item_id = video_id_match.group(1)
    share_url = f"https://www.douyin.com/video/{item_id}"

    # Dedicated folder for this video
    video_folder = os.path.join(output_dir, f"douyin_{item_id}")
    os.makedirs(video_folder, exist_ok=True)

    out_path = os.path.join(video_folder, f"douyin_{item_id}.mp4")
    cover_path = os.path.join(video_folder, "cover.jpg")

    try:
        session = requests.Session()
        # 1. Register dynamic ttwid session
        try:
            ttwid_payload = {
                'region': 'cn',
                'aid': 1768,
                'needFid': 'false',
                'service': 'www.ixigua.com',
                'migrate_info': {'ticket': '', 'source': 'node'},
                'cbUrlProtocol': 'https',
                'union': 'true'
            }
            session.post('https://ttwid.bytedance.com/ttwid/union/register/', json=ttwid_payload, timeout=5)
        except Exception as e:
            print(f"[download_douyin_no_watermark] ttwid registration warning: {e}")

        # 2. Query aweme feed API (Mobile client emulation - bypasses web anti-bot)
        mobile_headers = {
            'User-Agent': 'com.ss.android.ugc.aweme/230501 (Linux; U; Android 10; zh_CN; Pixel 4; Build/QQ3A.200805.001; Cronet/TTNetVersion:b4d74d15 2020-04-23 QuicVersion:0144d358 2020-03-24)',
            'Accept-Encoding': 'gzip, deflate',
        }
        feed_url = f'https://aweme.snssdk.com/aweme/v1/feed/?aweme_id={item_id}&version_code=230501&aid=1128'
        api_resp = session.get(feed_url, headers=mobile_headers, timeout=10)

        aweme = {}
        if api_resp.status_code == 200 and api_resp.text:
            try:
                data = api_resp.json()
                for item in data.get('aweme_list', []):
                    if str(item.get('aweme_id')) == item_id:
                        aweme = item
                        break
                if not aweme and data.get('aweme_list'):
                    aweme = data['aweme_list'][0]
            except Exception:
                pass

        # Fallback to web detail API if feed API returned empty
        if not aweme:
            web_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://www.douyin.com/'
            }
            detail_url = f'https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={item_id}&aid=1128&version_name=23.5.0&device_platform=android&os_version=2333'
            web_resp = session.get(detail_url, headers=web_headers, timeout=10)
            if web_resp.status_code == 200 and web_resp.text:
                try:
                    w_data = web_resp.json()
                    aweme = w_data.get("aweme_detail", {})
                except Exception:
                    pass

        if not aweme:
            # Check if video was already downloaded previously in default videos folder
            existing_candidates = [
                os.path.join(os.path.expanduser("~"), "Videos", "default", f"douyin_{item_id}.mp4"),
                os.path.join(os.path.expanduser("~"), "Videos", f"douyin_{item_id}.mp4"),
            ]
            for cand in existing_candidates:
                if os.path.exists(cand) and os.path.getsize(cand) > 0:
                    shutil.copy2(cand, out_path)
                    return {
                        "success": True,
                        "clean_url": share_url,
                        "video_dir": os.path.abspath(video_folder),
                        "file_path": os.path.abspath(out_path),
                        "cover_path": os.path.abspath(cover_path) if os.path.exists(cover_path) else None,
                        "cover_url": None,
                        "title": f"douyin_{item_id}",
                        "duration": 0,
                        "width": 1080,
                        "height": 1920,
                        "uploader": "Douyin User"
                    }
            return {"success": False, "error": "Douyin aweme_detail is empty", "file_path": None, "cover_path": None}

        title = aweme.get("desc", f"douyin_{item_id}")
        video_obj = aweme.get("video", {})
        play_addr = video_obj.get("play_addr", {})
        url_list = play_addr.get("url_list", [])

        if not url_list:
            return {"success": False, "error": "Douyin play URL not found in API response", "file_path": None, "cover_path": None}

        # Convert to no-watermark play URL
        raw_play_url = url_list[0]
        no_watermark_url = raw_play_url.replace("/playwm/", "/play/").replace("playwm", "play")

        # Download video stream
        video_resp = session.get(
            no_watermark_url,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            stream=True,
            timeout=30
        )
        if video_resp.status_code == 200:
            with open(out_path, "wb") as f:
                for chunk in video_resp.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)

            duration = int(video_obj.get("duration", 0)) // 1000 if video_obj.get("duration") else int(aweme.get("duration", 0)) // 1000
            width = video_obj.get("width", 1080)
            height = video_obj.get("height", 1920)
            uploader = aweme.get("author", {}).get("nickname", "Douyin User")

            # Extract and download cover/banner image (prioritize customized 'cover' banner over raw 'origin_cover' frame)
            cover_url = None
            for key in ("cover", "dynamic_cover", "origin_cover", "animated_cover"):
                urls = video_obj.get(key, {}).get("url_list", []) if isinstance(video_obj.get(key), dict) else []
                if urls:
                    cover_url = urls[0]
                    break

            if cover_url:
                try:
                    c_resp = session.get(cover_url, timeout=15)
                    if c_resp.status_code == 200:
                        with open(cover_path, "wb") as cf:
                            cf.write(c_resp.content)
                    else:
                        cover_path = None
                except Exception as c_err:
                    print(f"[download_douyin_no_watermark] Cover download warning: {c_err}")
                    cover_path = None
            else:
                cover_path = None

            # Save local metadata.json in video folder
            try:
                meta_file = os.path.join(video_folder, "metadata.json")
                with open(meta_file, "w", encoding="utf-8") as mf:
                    json.dump({
                        "id": item_id,
                        "title": title,
                        "duration": duration,
                        "width": width,
                        "height": height,
                        "uploader": uploader,
                        "clean_url": share_url,
                        "video_file": os.path.basename(out_path),
                        "cover_file": os.path.basename(cover_path) if cover_path else None,
                        "cover_url": cover_url,
                        "downloaded_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }, mf, ensure_ascii=False, indent=2)
            except Exception as mf_err:
                print(f"[download_douyin_no_watermark] Metadata write warning: {mf_err}")

            return {
                "success": True,
                "clean_url": share_url,
                "video_dir": os.path.abspath(video_folder),
                "file_path": os.path.abspath(out_path),
                "cover_path": os.path.abspath(cover_path) if cover_path and os.path.exists(cover_path) else None,
                "cover_url": cover_url,
                "title": title,
                "duration": duration,
                "width": width,
                "height": height,
                "uploader": uploader
            }
        else:
            return {"success": False, "error": f"Failed to download MP4 stream: HTTP {video_resp.status_code}", "file_path": None, "cover_path": None}
    except Exception as err:
        return {"success": False, "error": f"Douyin custom downloader error: {err}", "file_path": None, "cover_path": None}


def find_cookie_file() -> Optional[str]:
    """Find cookies.txt file in workspace or common directories."""
    candidates = [
        os.path.join(os.getcwd(), "cookies.txt"),
        os.path.join(os.getcwd(), "douyin_cookies.txt"),
        os.path.join(os.path.dirname(__file__), "cookies.txt"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "cookies.txt"),
    ]
    for c in candidates:
        if os.path.exists(c) and os.path.getsize(c) > 0:
            return os.path.abspath(c)
    return None


def download_with_ytdlp(url: str, output_dir: str = "downloads", filename_prefix: str = "video") -> dict:
    """
    Download video from any supported URL (YouTube, TikTok, Facebook, Instagram, Douyin, etc.) using yt-dlp
    or custom Douyin no-watermark engine.
    Saves each video and its banner/cover image into a dedicated subfolder.
    """
    import yt_dlp
    import json

    clean_url = clean_and_resolve_url(url)
    print(f"[download_with_ytdlp] Cleaned target URL: {clean_url}")

    cookie_file = find_cookie_file()
    if cookie_file:
        print(f"[download_with_ytdlp] Using cookies from: {cookie_file}")

    # 1. Custom Douyin handler (Bypasses yt-dlp cookie requirements if possible)
    if "douyin.com" in url or "iesdouyin.com" in url:
        print(f"[download_with_ytdlp] Douyin URL detected, using Douyin no-watermark engine...")
        dy_res = download_douyin_no_watermark(url, output_dir=output_dir)
        if dy_res.get("success"):
            return dy_res
        print(f"[download_with_ytdlp] Custom Douyin engine fallback: {dy_res.get('error')}, trying yt-dlp...")

    os.makedirs(output_dir, exist_ok=True)

    # Initial extraction options (metadata first to create dedicated folder)
    extract_opts = {
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }
    if cookie_file:
        extract_opts['cookiefile'] = cookie_file

    try:
        with yt_dlp.YoutubeDL(extract_opts) as ydl:
            info = ydl.extract_info(clean_url, download=False)
            if not info:
                raise Exception("yt-dlp could not extract video information")

            video_id = str(info.get("id") or int(time.time()))
            extractor = str(info.get("extractor_key") or filename_prefix).lower()
            folder_name = f"{extractor}_{video_id}"
            video_folder = os.path.join(output_dir, folder_name)
            os.makedirs(video_folder, exist_ok=True)

            outtmpl = os.path.join(video_folder, f"{filename_prefix}_%(id)s.%(ext)s")

            ydl_download_opts = {
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': outtmpl,
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
                'overwrites': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            if cookie_file:
                ydl_download_opts['cookiefile'] = cookie_file

            with yt_dlp.YoutubeDL(ydl_download_opts) as ydl_down:
                ydl_down.download([clean_url])
                filename = ydl_down.prepare_filename(info)

            # Check if merged to .mp4 or original extension
            mp4_candidate = os.path.splitext(filename)[0] + ".mp4"
            if os.path.exists(mp4_candidate):
                final_path = mp4_candidate
            elif os.path.exists(filename):
                final_path = filename
            else:
                # Fallback search inside video_folder
                files = [os.path.join(video_folder, f) for f in os.listdir(video_folder) if not f.startswith("cover.") and not f.endswith(".json")]
                final_path = files[0] if files else filename

            # Download banner / thumbnail image
            cover_url = info.get("thumbnail")
            if not cover_url and info.get("thumbnails"):
                cover_url = info["thumbnails"][-1].get("url")

            cover_path = os.path.join(video_folder, "cover.jpg")
            if cover_url:
                try:
                    t_resp = requests.get(
                        cover_url,
                        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'},
                        timeout=15
                    )
                    if t_resp.status_code == 200:
                        with open(cover_path, "wb") as tf:
                            tf.write(t_resp.content)
                    else:
                        cover_path = None
                except Exception as t_err:
                    print(f"[download_with_ytdlp] Thumbnail download warning: {t_err}")
                    cover_path = None
            else:
                cover_path = None

            # Save local metadata.json in video folder
            try:
                meta_file = os.path.join(video_folder, "metadata.json")
                with open(meta_file, "w", encoding="utf-8") as mf:
                    json.dump({
                        "id": video_id,
                        "title": info.get("title", "Video"),
                        "duration": info.get("duration", 0),
                        "width": info.get("width", 1080),
                        "height": info.get("height", 1920),
                        "uploader": info.get("uploader", ""),
                        "clean_url": clean_url,
                        "video_file": os.path.basename(final_path),
                        "cover_file": os.path.basename(cover_path) if cover_path else None,
                        "cover_url": cover_url,
                        "downloaded_at": time.strftime("%Y-%m-%d %H:%M:%S")
                    }, mf, ensure_ascii=False, indent=2)
            except Exception as mf_err:
                print(f"[download_with_ytdlp] Metadata write warning: {mf_err}")

            return {
                "success": True,
                "clean_url": clean_url,
                "video_dir": os.path.abspath(video_folder),
                "file_path": os.path.abspath(final_path),
                "cover_path": os.path.abspath(cover_path) if cover_path and os.path.exists(cover_path) else None,
                "cover_url": cover_url,
                "title": info.get("title", "Video"),
                "duration": info.get("duration", 0),
                "width": info.get("width", 1080),
                "height": info.get("height", 1920),
                "uploader": info.get("uploader", ""),
            }
    except Exception as e:
        print(f"[yt-dlp] Download error for {clean_url}: {e}")
        # Try Douyin fallback if cookie error
        if "douyin" in str(e).lower() or "cookies" in str(e).lower():
            dy_res = download_douyin_no_watermark(url, output_dir=output_dir)
            if dy_res.get("success"):
                return dy_res

        return {
            "success": False,
            "error": str(e),
            "clean_url": clean_url,
            "file_path": None,
            "cover_path": None,
            "video_dir": None
        }

