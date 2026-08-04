#!/usr/bin/env python3
"""
Social Media Multi-Platform Publisher Manager
----------------------------------------------
Integrates with provider adapters in `providers/` to handle multi-platform video publishing
for TikTok, YouTube, Facebook Page/Reels, Instagram, LinkedIn, Threads, etc.
"""

from __future__ import annotations

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "config.json"

# Import provider adapters
try:
    from providers.tiktok import TikTokProvider
    from providers.youtube import YouTubeProvider
    from providers.facebook import FacebookProvider
    from providers.instagram import InstagramProvider
    from providers.linkedin import LinkedInProvider
    from providers.threads import ThreadsProvider
    from providers.types import PublishContent, MediaType, PostType
    PROVIDERS_AVAILABLE = True
except ImportError as err:
    logger.warning(f"Could not import social providers: {err}")
    PROVIDERS_AVAILABLE = False


def load_config() -> dict:
    """Load configuration from config.json"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config.json: {e}")
    return {}


def save_config(cfg: dict) -> bool:
    """Save configuration to config.json"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving config.json: {e}")
        return False


def is_auto_publish_enabled() -> bool:
    """Check if auto publish mode is enabled in config"""
    cfg = load_config()
    auto_pub = cfg.get("auto_publish", {})
    return bool(auto_pub.get("enabled", False))


def set_auto_publish_enabled(enabled: bool) -> bool:
    """Toggle auto publish setting in config.json"""
    cfg = load_config()
    if "auto_publish" not in cfg:
        cfg["auto_publish"] = {}
    cfg["auto_publish"]["enabled"] = enabled
    return save_config(cfg)


def get_enabled_platforms() -> List[str]:
    """Get list of platforms configured & enabled for publishing"""
    cfg = load_config()
    creds = cfg.get("social_credentials", {})
    enabled_platforms = []
    for platform_name, pdata in creds.items():
        if isinstance(pdata, dict) and pdata.get("enabled", False):
            enabled_platforms.append(platform_name.lower())
    return enabled_platforms


class SocialPublisherManager:
    """Manager for multi-platform publishing operations"""

    def __init__(self, config_dict: Optional[dict] = None):
        self.config = config_dict or load_config()
        self.creds = self.config.get("social_credentials", {})
        self.auto_pub_cfg = self.config.get("auto_publish", {})

    def publish_video(
        self,
        video_path_or_url: str,
        caption: Optional[str] = None,
        title: Optional[str] = None,
        platforms: Optional[List[str]] = None,
        privacy_status: Optional[str] = "public",
        thumbnail_file: Optional[str] = None,
        tags: Optional[List[str]] = None,
        category_id: Optional[str] = "22",
        made_for_kids: Optional[bool] = False,
        extra: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """
        Publish a video file or URL to specified (or all enabled) social media platforms.

        Returns:
            Dict containing overall status, results per platform, and details.
        """
        if not PROVIDERS_AVAILABLE:
            return {
                "success": False,
                "error": "Thư viện social providers chưa được cài đặt hoặc thiếu dependency (httpx).",
                "results": {}
            }

        target_platforms = platforms or get_enabled_platforms()
        if not target_platforms:
            # Fall back to default_platforms in auto_publish config if specified
            target_platforms = self.auto_pub_cfg.get("default_platforms", [])

        default_cap = self.auto_pub_cfg.get("default_caption", "Video được tự động đăng bởi CapCutAPI")
        final_caption = caption or default_cap
        final_title = title or final_caption[:60]

        results = {}
        success_count = 0
        failed_count = 0

        extra_payload = dict(extra) if extra else {}
        if privacy_status:
            extra_payload["privacy_status"] = privacy_status
        if thumbnail_file:
            extra_payload["thumbnail_file"] = thumbnail_file
        if tags:
            extra_payload["tags"] = tags
        if category_id:
            extra_payload["category_id"] = category_id
        if made_for_kids is not None:
            extra_payload["self_declared_made_for_kids"] = made_for_kids

        # Create PublishContent payload
        content = PublishContent(
            text=final_caption,
            title=final_title,
            description=final_caption,
            post_type=PostType.VIDEO,
            media_files=[video_path_or_url] if not video_path_or_url.startswith("http") else [],
            media_urls=[video_path_or_url] if video_path_or_url.startswith("http") else [],
            extra=extra_payload
        )

        for plat in target_platforms:
            plat_name = plat.lower().strip()
            plat_creds = self.creds.get(plat_name, {})

            if not plat_creds.get("enabled", False) and not plat_creds.get("access_token"):
                results[plat_name] = {
                    "success": False,
                    "status": "SKIPPED",
                    "error": f"Nền tảng '{plat_name}' chưa được bật hoặc chưa cấu hình Access Token trong config.json."
                }
                continue

            access_token = plat_creds.get("access_token", "")
            if not access_token:
                results[plat_name] = {
                    "success": False,
                    "status": "SKIPPED",
                    "error": f"Thiếu access_token cho nền tảng {plat_name}."
                }
                continue

            try:
                pub_result = self._dispatch_publish(plat_name, plat_creds, access_token, content, video_path_or_url)
                if pub_result.get("success"):
                    success_count += 1
                else:
                    failed_count += 1
                results[plat_name] = pub_result
            except Exception as e:
                logger.error(f"Lỗi khi đăng bài lên {plat_name}: {e}")
                failed_count += 1
                results[plat_name] = {
                    "success": False,
                    "status": "ERROR",
                    "error": str(e)
                }

        overall_success = (success_count > 0)
        return {
            "success": overall_success,
            "total_requested": len(target_platforms),
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results
        }

    def _dispatch_publish(
        self,
        platform_name: str,
        creds: dict,
        access_token: str,
        content: PublishContent,
        file_path_or_url: str
    ) -> dict:
        """Dispatch publishing call to the appropriate provider adapter"""
        if platform_name == "tiktok":
            provider = TikTokProvider(credentials={
                "client_key": creds.get("client_key", ""),
                "client_secret": creds.get("client_secret", "")
            })
            res = provider.publish_post(access_token=access_token, content=content)
            return {
                "success": bool(res.platform_post_id),
                "post_id": res.platform_post_id,
                "post_url": res.url,
                "raw": res.extra
            }

        elif platform_name == "facebook":
            provider = FacebookProvider(credentials={})
            res = provider.publish_post(access_token=access_token, content=content)
            return {
                "success": bool(res.platform_post_id),
                "post_id": res.platform_post_id,
                "post_url": res.url,
                "raw": res.extra
            }

        elif platform_name == "youtube":
            provider = YouTubeProvider(credentials={
                "client_id": creds.get("client_id", ""),
                "client_secret": creds.get("client_secret", "")
            })
            refresh_tok = creds.get("refresh_token")
            if refresh_tok:
                try:
                    new_tokens = provider.refresh_token(refresh_tok)
                    if new_tokens and new_tokens.access_token:
                        access_token = new_tokens.access_token
                        logger.info("Tự động làm mới YouTube Access Token thành công!")
                except Exception as r_err:
                    logger.warning(f"Thử làm mới YouTube Refresh Token không thành công, thử dùng access_token có sẵn: {r_err}")

            res = provider.publish_post(access_token=access_token, content=content)
            return {
                "success": bool(res.platform_post_id),
                "post_id": res.platform_post_id,
                "post_url": res.url,
                "raw": res.extra
            }

        elif platform_name == "instagram":
            provider = InstagramProvider(credentials={})
            res = provider.publish_post(access_token=access_token, content=content)
            return {
                "success": bool(res.platform_post_id),
                "post_id": res.platform_post_id,
                "post_url": res.url,
                "raw": res.extra
            }

        elif platform_name == "linkedin":
            provider = LinkedInProvider(credentials={})
            res = provider.publish_post(access_token=access_token, content=content)
            return {
                "success": bool(res.platform_post_id),
                "post_id": res.platform_post_id,
                "post_url": res.url,
                "raw": res.extra
            }

        elif platform_name == "threads":
            provider = ThreadsProvider(credentials={})
            res = provider.publish(access_token=access_token, content=content)
            return {
                "success": bool(res.post_id),
                "post_id": res.post_id,
                "post_url": res.post_url,
                "raw": res.raw_response
            }

        else:
            return {
                "success": False,
                "error": f"Nền tảng '{platform_name}' chưa được hỗ trợ adapter trong social_publisher."
            }


def publish_video_auto(
    video_path_or_url: str,
    caption: Optional[str] = None,
    title: Optional[str] = None,
    platforms: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Helper function to execute auto publishing"""
    publisher = SocialPublisherManager()
    return publisher.publish_video(
        video_path_or_url=video_path_or_url,
        caption=caption,
        title=title,
        platforms=platforms
    )


if __name__ == "__main__":
    print("Testing SocialPublisherManager...")
    mgr = SocialPublisherManager()
    enabled = get_enabled_platforms()
    print(f"Auto-publish enabled: {is_auto_publish_enabled()}")
    print(f"Configured enabled platforms: {enabled}")
