#!/usr/bin/env python3
"""
MongoDB Database Integration Module (with Local JSON DB Fallback)
-----------------------------------------------------------------
Connects to MongoDB (database 'video_logger_db' -> collection 'videos').
If MongoDB is offline or not installed, automatically and transparently falls back
to a persistent local JSON database in logs/video_logger_db.json.
Handles video task logging, status updates, and history queries.
"""

import os
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path
from pymongo import MongoClient, errors

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.resolve()
ROOT_DIR = Path(__file__).resolve().parents[2]

CONFIG_FILE = BASE_DIR / "config.json"
ROOT_CONFIG_FILE = ROOT_DIR / "config.json"
ENV_FILE = ROOT_DIR / ".env"

LOGS_DIR = ROOT_DIR / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOCAL_DB_FILE = LOGS_DIR / "video_logger_db.json"


def load_db_config() -> dict:
    config = {}
    if ROOT_CONFIG_FILE.exists():
        try:
            with open(ROOT_CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception:
            pass

    if CONFIG_FILE.exists() and CONFIG_FILE != ROOT_CONFIG_FILE:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config.update(json.load(f))
        except Exception:
            pass

    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k in ("MONGODB_URI", "MONGO_URI") and not config.get("mongodb_uri"):
                            config["mongodb_uri"] = v
        except Exception:
            pass

    return config


config = load_db_config()
MONGO_URI = config.get("mongodb_uri", os.environ.get("MONGODB_URI", "mongodb://localhost:27017"))
DB_NAME = config.get("mongodb_db_name", "video_logger_db")
COLLECTION_NAME = config.get("mongodb_collection_name", "videos")

_client: Optional[MongoClient] = None


def get_db_client() -> Optional[MongoClient]:
    global _client
    if _client is None:
        try:
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1000)
            _client.admin.command('ping')
            logger.info(f"Connected to MongoDB at {MONGO_URI}")
        except errors.PyMongoError as e:
            logger.debug(f"Could not connect to MongoDB: {e}")
            _client = None
    return _client


def get_videos_collection():
    client = get_db_client()
    if client:
        return client[DB_NAME][COLLECTION_NAME]
    return None


# --- Local JSON Fallback DB Operations ---

def _load_local_db() -> Dict[str, Any]:
    if LOCAL_DB_FILE.exists():
        try:
            with open(LOCAL_DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error reading local db: {e}")
    return {"videos": {}}


def _save_local_db(data: Dict[str, Any]):
    try:
        with open(LOCAL_DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.error(f"Error writing local db: {e}")


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
    Save or update a video record in MongoDB and local JSON fallback store.
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    doc_id = str(uuid.uuid4())
    document = {
        "_id": doc_id,
        "videoUrl": video_url,
        "pageUrl": page_url or video_url,
        "pageTitle": page_title or "Telegram Download",
        "folderName": folder_name or "telegram",
        "status": status,
        "savedAt": now_iso,
        "updatedAt": now_iso,
        "telegramUserId": telegram_user_id,
        **(extra_meta or {})
    }

    # 1. Save to local fallback DB
    try:
        db_data = _load_local_db()
        existing_key = None
        for k, v in db_data.get("videos", {}).items():
            if v.get("videoUrl") == video_url or v.get("cleanUrl") == video_url:
                existing_key = k
                break
        if existing_key:
            db_data["videos"][existing_key].update({
                "status": status,
                "updatedAt": now_iso,
                **(extra_meta or {})
            })
            doc_id = existing_key
        else:
            db_data["videos"][doc_id] = document
        _save_local_db(db_data)
    except Exception as e:
        logger.error(f"Error updating local fallback DB: {e}")

    # 2. Save to MongoDB if available
    coll = get_videos_collection()
    if coll is not None:
        try:
            mongo_doc = dict(document)
            mongo_doc["savedAt"] = now
            mongo_doc["updatedAt"] = now
            del mongo_doc["_id"]
            existing = coll.find_one({"videoUrl": video_url})
            if existing:
                coll.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"status": status, "updatedAt": now, **(extra_meta or {})}}
                )
                return str(existing["_id"])
            else:
                result = coll.insert_one(mongo_doc)
                return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error saving to MongoDB: {e}")

    return doc_id


def update_video_status(
    video_url: str,
    status: str,
    draft_id: Optional[str] = None,
    local_path: Optional[str] = None,
    output_mp4: Optional[str] = None,
    error_msg: Optional[str] = None,
    cover_path: Optional[str] = None,
    video_dir: Optional[str] = None,
    **extra_fields
) -> bool:
    """
    Update status and metadata for a video task in MongoDB and local DB.
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    update_fields: Dict[str, Any] = {
        "status": status,
        "updatedAt": now_iso,
        **extra_fields
    }
    if draft_id:
        update_fields["draftId"] = draft_id
    if local_path:
        update_fields["localPath"] = local_path
    if output_mp4:
        update_fields["outputMp4"] = output_mp4
    if error_msg:
        update_fields["error"] = error_msg
    if cover_path:
        update_fields["coverPath"] = cover_path
    if video_dir:
        update_fields["videoDir"] = video_dir

    # 1. Update in local fallback DB
    try:
        db_data = _load_local_db()
        for k, v in db_data.get("videos", {}).items():
            if v.get("videoUrl") == video_url or v.get("cleanUrl") == video_url or (draft_id and v.get("draftId") == draft_id):
                v.update(update_fields)
        _save_local_db(db_data)
    except Exception as e:
        logger.error(f"Error updating local status: {e}")

    # 2. Update in MongoDB if available
    coll = get_videos_collection()
    if coll is not None:
        try:
            mongo_fields = dict(update_fields)
            mongo_fields["updatedAt"] = now
            res = coll.update_many(
                {"$or": [{"videoUrl": video_url}, {"cleanUrl": video_url}]},
                {"$set": mongo_fields}
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating MongoDB status: {e}")

    return True


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
    Log a pipeline execution step into MongoDB and local DB.
    """
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    step_entry = {
        "step": step_name,
        "status": status,
        "timestamp": now_iso,
        "detail": detail or ""
    }

    set_fields: Dict[str, Any] = {
        "status": status if status in ["FAILED", "COMPLETED"] else step_name.lower(),
        "currentStep": step_name,
        "updatedAt": now_iso
    }
    if render_config:
        set_fields["renderConfig"] = render_config
    if extra_meta:
        for k, v in extra_meta.items():
            set_fields[k] = v

    # 1. Update in local fallback DB
    try:
        db_data = _load_local_db()
        for k, v in db_data.get("videos", {}).items():
            if v.get("videoUrl") == video_url or v.get("cleanUrl") == video_url:
                v.update(set_fields)
                if "pipelineSteps" not in v or not isinstance(v["pipelineSteps"], list):
                    v["pipelineSteps"] = []
                v["pipelineSteps"].append(step_entry)
        _save_local_db(db_data)
    except Exception as e:
        logger.error(f"Error logging local pipeline step: {e}")

    # 2. Update in MongoDB if available
    coll = get_videos_collection()
    if coll is not None:
        try:
            mongo_fields = dict(set_fields)
            mongo_fields["updatedAt"] = now
            res = coll.update_many(
                {"$or": [{"videoUrl": video_url}, {"cleanUrl": video_url}]},
                {
                    "$set": mongo_fields,
                    "$push": {"pipelineSteps": step_entry}
                }
            )
            return res.modified_count > 0
        except Exception as e:
            logger.error(f"Error logging pipeline step to MongoDB: {e}")

    return True


def get_recent_videos(limit: int = 10, folder_name: Optional[str] = None) -> List[dict]:
    """
    Get recent video logs from MongoDB (or local fallback DB).
    """
    coll = get_videos_collection()
    if coll is not None:
        query = {}
        if folder_name:
            query["folderName"] = folder_name
        try:
            cursor = coll.find(query).sort("savedAt", -1).limit(limit)
            results = []
            for doc in cursor:
                doc["_id"] = str(doc["_id"])
                results.append(doc)
            return results
        except Exception as e:
            logger.error(f"Error reading from MongoDB: {e}")

    # Fallback to local DB
    try:
        db_data = _load_local_db()
        videos = list(db_data.get("videos", {}).values())
        if folder_name:
            videos = [v for v in videos if v.get("folderName") == folder_name]
        videos.sort(key=lambda x: x.get("updatedAt", ""), reverse=True)
        return videos[:limit]
    except Exception as e:
        logger.error(f"Error reading local fallback db: {e}")
        return []


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("Testing DB connection & local fallback...")
    coll = get_videos_collection()
    if coll is not None:
        print(f"✅ Connected to MongoDB '{DB_NAME}.{COLLECTION_NAME}' successfully!")
    else:
        print("ℹ️ MongoDB is offline; using persistent local JSON store at:", LOCAL_DB_FILE)
    recent = get_recent_videos(limit=3)
    print(f"Found {len(recent)} recent videos in DB.")

