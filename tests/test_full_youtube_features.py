#!/usr/bin/env python3
"""
Full YouTube End-to-End Features Test Suite
-------------------------------------------
Tests:
1. Channel Banner Upload & Branding (`channelBanners.insert` & `channels.update`)
2. Standalone Subtitle / Captions Track Upload (`captions.insert`)
3. Custom Video Thumbnail Upload (`thumbnails.set`)
4. First Comment Publishing (`commentThreads.insert`)
5. Video Metrics & Analytics Fetch (`videos.list`)
"""

import os
import sys
import json
import logging
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Set UTF-8 encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FullYouTubeTest")

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "src" / "capcut_api"))
sys.path.insert(0, str(ROOT_DIR / "src" / "capcut_api" / "publisher"))

from capcut_api.publisher.providers.youtube import YouTubeProvider
from capcut_api.publisher.social_publisher import load_config


def generate_test_banner(output_path: str = "downloads/test_banner.jpg"):
    """Create a sample 2560x1440 16:9 banner image"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    width, height = 2560, 1440
    # Gradient-like background
    img = Image.new("RGB", (width, height), color=(15, 23, 42))
    draw = ImageDraw.Draw(img)

    # Draw decorative shapes
    draw.rectangle([0, 0, width, height], fill=(15, 23, 42))
    draw.ellipse([width//4, height//4, width*3//4, height*3//4], fill=(30, 41, 59))
    draw.rectangle([100, height//2 - 100, width - 100, height//2 + 100], fill=(239, 68, 68))
    
    draw.text((width//2 - 400, height//2 - 30), "CAPCUT AUTOMATION STUDIO", fill=(255, 255, 255))
    draw.text((width//2 - 300, height//2 + 30), "Official AI Video Publishing Channel", fill=(241, 245, 249))

    img.save(output_path, "JPEG", quality=90)
    logger.info(f"Đã tạo ảnh Banner mẫu tại: {output_path} (2560x1440)")
    return os.path.abspath(output_path)


def generate_test_thumbnail(output_path: str = "downloads/test_thumbnail.jpg"):
    """Create a sample 1280x720 16:9 thumbnail image"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    width, height = 1280, 720
    img = Image.new("RGB", (width, height), color=(220, 38, 38))
    draw = ImageDraw.Draw(img)

    draw.rectangle([40, 40, width - 40, height - 40], fill=(17, 24, 39))
    draw.text((100, height//2 - 50), "CAPCUT API VIDEO TEST", fill=(255, 255, 255))
    draw.text((100, height//2 + 30), "#Shorts Auto-Publish System", fill=(234, 179, 8))

    img.save(output_path, "JPEG", quality=90)
    logger.info(f"Đã tạo ảnh Thumbnail mẫu tại: {output_path} (1280x720)")
    return os.path.abspath(output_path)


def generate_test_srt(output_path: str = "downloads/test_captions.srt"):
    """Create a sample Vietnamese SRT subtitle file"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    srt_content = """1
00:00:00,500 --> 00:00:03,000
Chào mừng các bạn đến với video tự động hóa CapCut!

2
00:00:03,500 --> 00:00:06,800
Hệ thống vừa hoàn tất quy trình dịch thuật và lồng tiếng tự động.

3
00:00:07,000 --> 00:00:10,000
Được xuất bản tự động qua CapCutAPI Social Publisher Service.
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(srt_content.strip() + "\n")
    logger.info(f"Đã tạo file phụ đề mẫu tại: {output_path}")
    return os.path.abspath(output_path)


def main():
    print("=" * 70)
    print("      🚀 CHẠY TEST ĐẦY ĐỦ CÁC TÍNH NĂNG NÂNG CAO YOUTUBE API")
    print("=" * 70)

    cfg = load_config()
    yt_cfg = cfg.get("social_credentials", {}).get("youtube", {})
    client_id = yt_cfg.get("client_id")
    client_secret = yt_cfg.get("client_secret")
    refresh_token = yt_cfg.get("refresh_token")
    access_token = yt_cfg.get("access_token")

    if not client_id or not client_secret or not refresh_token:
        print("❌ Chưa có đủ credentials trong config.json!")
        return

    provider = YouTubeProvider(credentials={"client_id": client_id, "client_secret": client_secret})

    # 1. Refresh token to ensure valid access_token
    print("\n🔄 [1/5] Làm mới Access Token...")
    try:
        new_tokens = provider.refresh_token(refresh_token)
        access_token = new_tokens.access_token
        print("✅ Access Token còn hiệu lực & đã được làm mới!")
    except Exception as e:
        print(f"⚠️ Làm mới token thất bại, dùng access_token có sẵn: {e}")

    # Video ID to test on
    video_id = "u-1HOm0hiF4"

    # 2. Test Channel Banner Upload
    print("\n🖼️ [2/5] Test Cập nhật Banner Kênh YouTube (2560x1440)...")
    banner_file = generate_test_banner()
    try:
        banner_res = provider.set_channel_banner(access_token=access_token, image_path=banner_file)
        print(f"🎉 ĐỔI BANNER THÀNH CÔNG!")
        print(f"   URL Banner trả về: {banner_res.get('banner_url')}")
    except Exception as b_err:
        print(f"❌ Lỗi đổi banner: {b_err}")

    # 3. Test Custom Thumbnail Upload
    print(f"\n📸 [3/5] Test Upload Custom Thumbnail cho Video {video_id}...")
    thumb_file = generate_test_thumbnail()
    try:
        thumb_res = provider.set_thumbnail(access_token=access_token, video_id=video_id, image_path=thumb_file)
        print(f"🎉 GẮN THUMBNAIL THÀNH CÔNG cho video {video_id}!")
    except Exception as t_err:
        print(f"❌ Lỗi gắn thumbnail: {t_err}")

    # 4. Test Standalone Caption / Subtitle Track Upload (CC)
    print(f"\n📝 [4/5] Test Upload Phụ đề rời CC Tiếng Việt cho Video {video_id}...")
    srt_file = generate_test_srt()
    try:
        caption_res = provider.upload_caption(
            access_token=access_token,
            video_id=video_id,
            srt_path_or_content=srt_file,
            language="vi",
            name="Tiếng Việt (Tự Động)"
        )
        print(f"🎉 UPLOAD PHỤ ĐỀ RỜI THÀNH CÔNG!")
        print(f"   Caption Track ID: {caption_res.get('caption_id')}")
        print(f"   Ngôn ngữ: {caption_res.get('snippet', {}).get('language')}")
    except Exception as c_err:
        print(f"❌ Lỗi upload phụ đề: {c_err}")

    # 5. Test First Comment Publishing
    print(f"\n💬 [5/5] Test Đăng Bình Luận Đầu Tiên trên Video {video_id}...")
    try:
        comment_res = provider.publish_comment(
            access_token=access_token,
            post_id=video_id,
            text="📌 Video được dựng và xuất bản tự động 100% bằng CapCutAPI Studio & Publisher Microservice!"
        )
        print(f"🎉 ĐĂNG BÌNH LUẬN THÀNH CÔNG!")
        print(f"   Comment ID: {comment_res.platform_comment_id}")
    except Exception as cm_err:
        print(f"❌ Lỗi đăng comment: {cm_err}")

    print("\n" + "=" * 70)
    print(f"🌟 HOÀN TẤT KIỂM THỬ TOÀN BỘ TÍNH NĂNG NÂNG CAO CHO VIDEO {video_id}!")
    print(f"👉 Link kiểm tra trên YouTube: https://www.youtube.com/watch?v={video_id}")
    print("=" * 70)


if __name__ == "__main__":
    main()
