#!/usr/bin/env python3
"""
MongoDB Database Integration Module
-----------------------------------
Connects to MongoDB (same database 'video_logger_db' as send-to-webhook).
Handles video task logging, status updates, and history queries.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path
from pymongo import MongoClient, errors

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.resolve()
CONFIG_FILE = BASE_DIR / "config.json"


def load_db_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


config = load_db_config()
MONGO_URI = config.get("mongodb_uri", "mongodb://localhost:27017")
DB_NAME = config.get("mongodb_db_name", "video_logger_db")
COLLECTION_NAME = config.get("mongodb_collection_name", "videos")

_client: Optional[MongoClient] = None


def get_db_client() -> Optional[MongoClient]:
    global _client
    if _client is None:
        try:
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            _client.admin.command('ping')
            logger.info(f"Connected to MongoDB at {MONGO_URI}")
        except errors.PyMongoError as e:
            logger.warning(f"Could not connect to MongoDB: {e}")
            _client = None
    return _client


def get_videos_collection():
    client = get_db_client()
    if client:
        return client[DB_NAME][COLLECTION_NAME]
    return None


def save_video_log(
    video_url: str,
    page_url: Optional[str] = None,
    page_title: Optional[str] = None,
    folder_name: str = "telegram",
    status: str = "pending",
    telegram_user_id: Optional[int] = None,
    extra_meta: Optional[dict] = None
) -> Optional[str]:
    """
    Save or update a video record in MongoDB (video_logger_db -> videos).
    Compatible with send-to-webhook schema.
    """
    coll = get_videos_collection()
    if coll is None:
        logger.warning("MongoDB collection unavailable. Skipping save_video_log.")
        return None

    now = datetime.now(timezone.utc)
    document = {
        "videoUrl": video_url,
        "pageUrl": page_url or video_url,
        "pageTitle": page_title or "Telegram Download",
        "folderName": folder_name or "telegram",
        "status": status,
        "savedAt": now,
        "updatedAt": now,
        "telegramUserId": telegram_user_id,
        **(extra_meta or {})
    }

    try:
        # Check if already exists by videoUrl
        existing = coll.find_one({"videoUrl": video_url})
        if existing:
            coll.update_one(
                {"_id": existing["_id"]},
                {"$set": {"status": status, "updatedAt": now, **(extra_meta or {})}}
            )
            return str(existing["_id"])
        else:
            result = coll.insert_one(document)
            return str(result.inserted_id)
    except Exception as e:
        logger.error(f"Error saving to MongoDB: {e}")
        return None


def update_video_status(
    video_url: str,
    status: str,
    draft_id: Optional[str] = None,
    local_path: Optional[str] = None,
    output_mp4: Optional[str] = None,
    error_msg: Optional[str] = None
) -> bool:
    """
    Update status and metadata for a video task in MongoDB.
    """
    coll = get_videos_collection()
    if coll is None:
        return False

    update_fields: Dict[str, Any] = {
        "status": status,
        "updatedAt": datetime.now(timezone.utc)
    }

    if draft_id:
        update_fields["draftId"] = draft_id
    if local_path:
        update_fields["localPath"] = local_path
    if output_mp4:
        update_fields["outputMp4"] = output_mp4
    if error_msg:
        update_fields["error"] = error_msg

    try:
        res = coll.update_many(
            {"$or": [{"videoUrl": video_url}, {"cleanUrl": video_url}]},
            {"$set": update_fields}
        )
        return res.modified_count > 0
    except Exception as e:
        logger.error(f"Error updating MongoDB status: {e}")
        return False


def get_default_render_config(width: int = 1080, height: int = 1920) -> dict:
    """Default render configuration for CapCut pipeline"""
    return {
        "width": width,
        "height": height,
        "ratio": "9:16" if height > width else "16:9",
        "fps": 30,
        "speed": 1.0,
        "volume": 1.0,
        "autoCaptions": True,
        "ttsVoice": "Vietnamese_Female",
        "blurEffect": True,
        "exportFormat": "mp4"
    }


def log_pipeline_step(
    video_url: str,
    step_name: str,
    status: str = "SUCCESS",
    detail: Optional[str] = None,
    render_config: Optional[dict] = None,
    extra_meta: Optional[dict] = None
) -> bool:
    """
    Log a pipeline execution step into MongoDB.
    Pushes step into 'pipelineSteps' array, updates 'currentStep', 'status', and 'renderConfig'.
    """
    coll = get_videos_collection()
    if coll is None:
        return False

    now_iso = datetime.now(timezone.utc).isoformat()
    now_dt = datetime.now(timezone.utc)

    step_entry = {
        "step": step_name,
        "status": status,
        "timestamp": now_iso,
        "detail": detail or ""
    }

    set_fields: Dict[str, Any] = {
        "status": status if status in ["FAILED", "COMPLETED"] else step_name.lower(),
        "currentStep": step_name,
        "updatedAt": now_dt
    }

    if render_config:
        set_fields["renderConfig"] = render_config
    if extra_meta:
        for k, v in extra_meta.items():
            set_fields[k] = v

    try:
        res = coll.update_many(
            {"$or": [{"videoUrl": video_url}, {"cleanUrl": video_url}]},
            {
                "$set": set_fields,
                "$push": {"pipelineSteps": step_entry}
            }
        )
        return res.modified_count > 0
    except Exception as e:
        logger.error(f"Error logging pipeline step to MongoDB: {e}")
        return False


def get_recent_videos(limit: int = 10, folder_name: Optional[str] = None) -> List[dict]:
    """
    Get recent video logs from MongoDB.
    """
    coll = get_videos_collection()
    if coll is None:
        return []

    query = {}
    if folder_name:
        query["folderName"] = folder_name

    try:
        cursor = coll.find(query).sort("savedAt", -1).limit(limit)
        results = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"]) # convert ObjectId to string
            results.append(doc)
        return results
    except Exception as e:
        logger.error(f"Error reading from MongoDB: {e}")
        return []


if __name__ == "__main__":
    print("Testing MongoDB connection...")
    coll = get_videos_collection()
    if coll is not None:
        print(f"✅ Connected to MongoDB '{DB_NAME}.{COLLECTION_NAME}' successfully!")
        recent = get_recent_videos(limit=3)
        print(f"Found {len(recent)} recent videos in DB.")
    else:
        print("❌ MongoDB service is not running or connection failed.")
