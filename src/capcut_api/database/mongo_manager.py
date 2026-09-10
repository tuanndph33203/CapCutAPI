"""
MongoDB & Local Database Manager for CapCut Recap Automation
============================================================
Provides unified database storage for:
1. Scripts (Full cinematic recap scripts, scenes, voiceovers, timeline, % chapter mapping)
2. Projects (Pipeline project configurations, metadata, render states)
3. Media Assets (Tracking files on Google Drive and local cache)

Features:
- Connects to MongoDB Atlas (Free M0 or custom) via pymongo.
- Automatic Graceful Fallback to Local JSON Storage if MongoDB URI is not configured
  or if network is offline (Zero-Breaking Guarantee).
"""

import os
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("DatabaseManager")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_FILE = ROOT_DIR / "config.json"
FALLBACK_DIR = ROOT_DIR / "data" / "database_fallback"


class DatabaseManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: Optional[Path] = None):
        if self._initialized:
            return
        self.config_path = config_path or CONFIG_FILE
        self.fallback_dir = FALLBACK_DIR
        self.fallback_dir.mkdir(parents=True, exist_ok=True)
        (self.fallback_dir / "scripts").mkdir(exist_ok=True)
        (self.fallback_dir / "projects").mkdir(exist_ok=True)
        (self.fallback_dir / "media").mkdir(exist_ok=True)
        (self.fallback_dir / "scenes_analysis").mkdir(exist_ok=True)

        self.client = None
        self.db = None
        self.is_connected = False
        self.connection_mode = "local_fallback"
        self.db_name = "capcut_recap_ai"
        self.mongo_uri = ""

        self._init_connection()
        self._initialized = True

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Lỗi đọc file config: {e}")
        return {}

    def _init_connection(self):
        """Khởi tạo kết nối MongoDB Atlas hoặc chuyển về Fallback."""
        cfg = self._load_config()
        db_cfg = cfg.get("database", {})
        self.mongo_uri = os.environ.get("MONGODB_URI", db_cfg.get("mongodb_uri", "")).strip()
        self.db_name = db_cfg.get("database_name", "capcut_recap_ai")

        if not self.mongo_uri:
            logger.info("ℹ️ Không tìm thấy MongoDB URI trong config -> Sử dụng Local JSON Storage fallback.")
            self.connection_mode = "local_fallback"
            self.is_connected = False
            return

        try:
            import pymongo
            logger.info("⏳ Đang kết nối tới MongoDB Atlas...")
            # Timeout 3s để tránh lag hệ thống khi mạng chậm
            self.client = pymongo.MongoClient(
                self.mongo_uri,
                serverSelectionTimeoutMS=3000,
                connectTimeoutMS=3000
            )
            # Kiểm tra ping thực tế
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            self.is_connected = True
            self.connection_mode = "mongodb"
            logger.info(f"✅ Kết nối MongoDB Atlas thành công! Database: '{self.db_name}'")

            # Tạo index tối ưu tìm kiếm
            try:
                self.db.scripts.create_index([("novel_id", 1), ("target_episode", 1)])
                self.db.scripts.create_index([("created_at", -1)])
                self.db.projects.create_index([("id", 1)], unique=True)
                self.db.scenes_analysis.create_index([("doc_id", 1)], unique=True)
                self.db.scenes_analysis.create_index([("novel_id", 1), ("episode_num", 1)])
                self.db.scenes_analysis.create_index([("created_at", -1)])
            except Exception as idx_err:
                logger.debug(f"Index creation note: {idx_err}")

        except Exception as conn_err:
            logger.warning(f"⚠️ Không thể kết nối MongoDB Atlas: {conn_err}. Tự động fallback sang Local JSON Storage.")
            self.client = None
            self.db = None
            self.is_connected = False
            self.connection_mode = "local_fallback"

    def get_status(self) -> Dict[str, Any]:
        """Trả về trạng thái hiện tại của Database."""
        status = {
            "mode": self.connection_mode,
            "is_connected": self.is_connected,
            "database_name": self.db_name,
            "has_uri_configured": bool(self.mongo_uri),
            "scripts_count": 0,
            "projects_count": 0
        }

        if self.is_connected and self.db is not None:
            try:
                status["scripts_count"] = self.db.scripts.count_documents({})
                status["projects_count"] = self.db.projects.count_documents({})
            except Exception:
                pass
        else:
            try:
                status["scripts_count"] = len(list((self.fallback_dir / "scripts").glob("*.json")))
                status["projects_count"] = len(list((self.fallback_dir / "projects").glob("*.json")))
            except Exception:
                pass

        return status

    # =========================================================================
    # SCRIPTS CRUD (Kịch bản phân cảnh)
    # =========================================================================

    def save_script(
        self,
        novel_id: str,
        target_episode: int,
        script_data: Dict[str, Any],
        detection_info: Optional[Dict[str, Any]] = None,
        custom_prompt: str = ""
    ) -> Dict[str, Any]:
        """Lưu trữ kịch bản hoàn chỉnh (12 cảnh, voiceover, %, timeline)."""
        now = int(time.time() * 1000)
        clean_novel = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "novel"
        script_id = f"{clean_novel}_ep{target_episode}_{int(time.time())}"

        doc = {
            "script_id": script_id,
            "novel_id": novel_id,
            "novel_title": script_data.get("title") or novel_id,
            "target_episode": target_episode,
            "reference_episode": (detection_info or {}).get("reference_episode", target_episode - 1 if target_episode > 1 else 1),
            "custom_prompt": custom_prompt,
            "title": script_data.get("title", f"Kịch bản Tập {target_episode}"),
            "opening_hook": script_data.get("opening_hook", ""),
            "closing_outro": script_data.get("closing_outro", ""),
            "scenes": script_data.get("scenes", []),
            "scenes_count": len(script_data.get("scenes", [])),
            "full_plain_text": script_data.get("full_plain_text", ""),
            "detection_info": detection_info or {},
            "total_words": script_data.get("total_words", 0),
            "est_duration_min": script_data.get("est_duration_min", 0.0),
            "created_at": now,
            "updated_at": now
        }

        # Lưu MongoDB nếu online
        if self.is_connected and self.db is not None:
            try:
                self.db.scripts.update_one(
                    {"script_id": script_id},
                    {"$set": doc},
                    upsert=True
                )
                logger.info(f"✅ Đã lưu kịch bản '{script_id}' vào MongoDB Atlas!")
            except Exception as e:
                logger.error(f"Lỗi lưu script vào MongoDB: {e}. Lưu vào fallback...")
                self._save_script_local(script_id, doc)
        else:
            self._save_script_local(script_id, doc)

        return doc

    def _save_script_local(self, script_id: str, doc: Dict[str, Any]):
        out_file = self.fallback_dir / "scripts" / f"{script_id}.json"
        out_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"💾 Đã lưu kịch bản vào Local JSON fallback: {out_file.name}")

    def get_script(self, script_id: str) -> Optional[Dict[str, Any]]:
        """Lấy chi tiết kịch bản theo ID."""
        if self.is_connected and self.db is not None:
            try:
                res = self.db.scripts.find_one({"script_id": script_id}, {"_id": 0})
                if res:
                    return res
            except Exception as e:
                logger.warning(f"Lỗi đọc script từ MongoDB: {e}")

        # Fallback local
        f = self.fallback_dir / "scripts" / f"{script_id}.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def list_scripts(self, novel_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Lấy danh sách các kịch bản đã tạo (sắp xếp mới nhất)."""
        scripts = []

        if self.is_connected and self.db is not None:
            try:
                query = {"novel_id": novel_id} if novel_id else {}
                cursor = self.db.scripts.find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
                scripts = list(cursor)
                return scripts
            except Exception as e:
                logger.warning(f"Lỗi query scripts từ MongoDB: {e}")

        # Fallback local
        files = sorted((self.fallback_dir / "scripts").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if novel_id and data.get("novel_id") != novel_id:
                    continue
                scripts.append(data)
            except Exception:
                continue
        return scripts

    def delete_script(self, script_id: str) -> bool:
        """Xóa kịch bản theo ID."""
        deleted = False
        if self.is_connected and self.db is not None:
            try:
                res = self.db.scripts.delete_one({"script_id": script_id})
                if res.deleted_count > 0:
                    deleted = True
            except Exception as e:
                logger.warning(f"Lỗi xóa script trên MongoDB: {e}")

        f = self.fallback_dir / "scripts" / f"{script_id}.json"
        if f.exists():
            try:
                f.unlink()
                deleted = True
            except Exception:
                pass
        return deleted

    # =========================================================================
    # PROJECTS CRUD (Quản lý dự án Pipeline)
    # =========================================================================

    def save_project(self, project_id: str, project_data: Dict[str, Any]) -> Dict[str, Any]:
        now = int(time.time() * 1000)
        project_data["updated_at"] = now
        if "created_at" not in project_data:
            project_data["created_at"] = now
        project_data["id"] = project_id

        if self.is_connected and self.db is not None:
            try:
                self.db.projects.update_one(
                    {"id": project_id},
                    {"$set": project_data},
                    upsert=True
                )
            except Exception as e:
                logger.warning(f"Lỗi lưu project MongoDB: {e}")

        # Luôn đồng bộ local
        f = self.fallback_dir / "projects" / f"{project_id}.json"
        f.write_text(json.dumps(project_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return project_data

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        if self.is_connected and self.db is not None:
            try:
                res = self.db.projects.find_one({"id": project_id}, {"_id": 0})
                if res:
                    return res
            except Exception:
                pass

        f = self.fallback_dir / "projects" / f"{project_id}.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
        return None

    def list_projects(self) -> List[Dict[str, Any]]:
        if self.is_connected and self.db is not None:
            try:
                return list(self.db.projects.find({}, {"_id": 0}).sort("updated_at", -1))
            except Exception:
                pass

        projects = []
        for f in (self.fallback_dir / "projects").glob("*.json"):
            try:
                projects.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        projects.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
        return projects

    # =========================================================================
    # SCENE ANALYSIS CRUD (Mô tả phân cảnh, lời thoại & đường dẫn ảnh Keyframes)
    # Hỗ trợ chuyển đổi máy tính liền mạch qua MongoDB Atlas & Google Drive 5TB
    # =========================================================================

    def save_scene_analysis(
        self,
        novel_id: str,
        episode_num: int,
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Lưu toàn bộ mô tả phân cảnh, prompt hình ảnh, kịch bản thuyết minh và
        đường dẫn ảnh keyframes vào MongoDB Atlas (kèm fallback local và GDrive).
        """
        now = int(time.time() * 1000)
        clean_novel = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "novel"
        doc_id = f"{clean_novel}_ep{episode_num}"

        # Đảm bảo các đường dẫn ảnh là đường dẫn tương đối chuẩn cho Cloud
        scenes = metadata.get("scenes", [])
        standardized_scenes = []
        for idx, sc in enumerate(scenes, 1):
            kf_name = sc.get("keyframe_filename") or f"keyframe_{idx:03d}_{int(sc.get('target_frame_time', 0))}s.jpg"
            rel_kf_path = f"scene_analysis/{clean_novel}/tap_{episode_num}/keyframes/{kf_name}"
            
            sc_item = dict(sc)
            sc_item["scene_id"] = sc.get("scene_id", sc.get("moment_index", idx))
            sc_item["keyframe_filename"] = kf_name
            sc_item["relative_keyframe_path"] = rel_kf_path
            sc_item["cloud_gdrive_folder"] = f"CapCutRecapAI/scene_analysis/{clean_novel}/tap_{episode_num}"
            sc_item["thumbnail_url"] = f"/api/novel/scenes/thumbnail?novel_id={clean_novel}&episode={episode_num}&filename={kf_name}"
            sc_item["download_url"] = f"/api/cloud/download?relative_path={rel_kf_path}"
            
            # Bảo đảm có các trường mô tả
            if "action_summary" not in sc_item:
                sc_item["action_summary"] = sc_item.get("scene_title") or sc_item.get("visual_description", "")
            if "visual_prompt" not in sc_item:
                sc_item["visual_prompt"] = sc_item.get("visual_description") or sc_item.get("scene_title", "")
            if "voiceover" not in sc_item:
                sc_item["voiceover"] = sc_item.get("srt_dialogue", "")
            if "estimated_duration_sec" not in sc_item:
                dur = float(sc_item.get("end_time", 0)) - float(sc_item.get("start_time", 0))
                sc_item["estimated_duration_sec"] = max(round(dur, 2), 3.0) if dur > 0 else 5.0

            standardized_scenes.append(sc_item)

        doc = {
            "doc_id": doc_id,
            "novel_id": clean_novel,
            "novel_name": metadata.get("novel_name", clean_novel),
            "episode_num": episode_num,
            "video_filename": metadata.get("video_filename", ""),
            "video_source": metadata.get("video_source", ""),
            "analyzed_at": metadata.get("analyzed_at", now),
            "processing_time_sec": metadata.get("processing_time_sec", 0.0),
            "scenes_count": len(standardized_scenes),
            "srt_segments_count": metadata.get("srt_segments_count", len(standardized_scenes)),
            "gdrive_relative_folder": f"scene_analysis/{clean_novel}/tap_{episode_num}",
            "srt_relative_path": f"scene_analysis/{clean_novel}/tap_{episode_num}/tap_{episode_num}.srt",
            "scenes": standardized_scenes,
            "updated_at": now
        }
        if "created_at" not in metadata:
            doc["created_at"] = now
        else:
            doc["created_at"] = metadata["created_at"]

        # 1. Lưu vào MongoDB Atlas nếu có kết nối
        if self.is_connected and self.db is not None:
            try:
                self.db.scenes_analysis.update_one(
                    {"doc_id": doc_id},
                    {"$set": doc},
                    upsert=True
                )
                logger.info(f"✅ Đã lưu Phân tích Phân cảnh '{doc_id}' ({len(standardized_scenes)} scenes) vào MongoDB Atlas!")
            except Exception as e:
                logger.warning(f"Lỗi lưu scene analysis vào MongoDB: {e}")

        # 2. Lưu vào local JSON fallback
        f = self.fallback_dir / "scenes_analysis" / f"{doc_id}.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

        # 3. Đồng bộ vào Google Drive 5TB nếu đang mount
        try:
            from capcut_api.cloud.gdrive_manager import get_gdrive_manager
            gdrive_mgr = get_gdrive_manager()
            gdrive_scenes = gdrive_mgr.get_scene_analysis_dir() / clean_novel / f"tap_{episode_num}"
            gdrive_scenes.mkdir(parents=True, exist_ok=True)
            (gdrive_scenes / "scenes_analysis.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.debug(f"Không thể ghi scenes_analysis.json trên Drive: {e}")

        return doc

    def get_scene_analysis(self, novel_id: str, episode_num: int) -> Optional[Dict[str, Any]]:
        """
        Lấy chi tiết phân tích phân cảnh:
        1. Ưu tiên đọc từ MongoDB Atlas (hỗ trợ chuyển máy bất kỳ).
        2. Nếu chưa có hoặc offline, đọc từ Google Drive scenes_analysis.json.
        3. Fallback đọc từ thư mục local.
        """
        clean_novel = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "novel"
        doc_id = f"{clean_novel}_ep{episode_num}"

        # 1. Kiểm tra MongoDB Atlas
        if self.is_connected and self.db is not None:
            try:
                res = self.db.scenes_analysis.find_one({"doc_id": doc_id}, {"_id": 0})
                if res:
                    return res
                # Thử tìm theo novel_id và episode_num
                res2 = self.db.scenes_analysis.find_one({
                    "$or": [
                        {"novel_id": clean_novel, "episode_num": episode_num},
                        {"novel_id": novel_id, "episode_num": episode_num}
                    ]
                }, {"_id": 0})
                if res2:
                    return res2
            except Exception as e:
                logger.warning(f"Lỗi đọc scene analysis từ MongoDB: {e}")

        # 2. Kiểm tra Google Drive 5TB
        try:
            from capcut_api.cloud.gdrive_manager import get_gdrive_manager
            gdrive_mgr = get_gdrive_manager()
            gdrive_json = gdrive_mgr.get_scene_analysis_dir() / clean_novel / f"tap_{episode_num}" / "scenes_analysis.json"
            if gdrive_json.exists():
                return json.loads(gdrive_json.read_text(encoding="utf-8"))
            gdrive_json2 = gdrive_mgr.get_scene_analysis_dir() / novel_id / f"tap_{episode_num}" / "scenes_analysis.json"
            if gdrive_json2.exists():
                return json.loads(gdrive_json2.read_text(encoding="utf-8"))
        except Exception:
            pass

        # 3. Fallback thư mục local
        f = self.fallback_dir / "scenes_analysis" / f"{doc_id}.json"
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Thử data/scene_analysis local
        local_json = ROOT_DIR / "data" / "scene_analysis" / clean_novel / f"tap_{episode_num}" / "scenes_analysis.json"
        if local_json.exists():
            try:
                return json.loads(local_json.read_text(encoding="utf-8"))
            except Exception:
                pass

        return None

    def list_scenes_analysis(self, novel_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách các tập phim đã phân tích phân cảnh."""
        episodes_list = []
        seen_keys = set()

        # 1. Lấy từ MongoDB Atlas
        if self.is_connected and self.db is not None:
            try:
                query = {}
                if novel_id:
                    clean_n = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip()
                    query = {"$or": [{"novel_id": novel_id}, {"novel_id": clean_n}]}
                cursor = self.db.scenes_analysis.find(query, {"_id": 0, "scenes": 0}).sort("episode_num", -1)
                for item in cursor:
                    k = f"{item.get('novel_id')}_ep{item.get('episode_num')}"
                    if k not in seen_keys:
                        seen_keys.add(k)
                        episodes_list.append(item)
            except Exception as e:
                logger.warning(f"Lỗi list scenes analysis từ MongoDB: {e}")

        # 2. Bổ sung từ Google Drive & Local Fallback
        for f in (self.fallback_dir / "scenes_analysis").glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                k = f"{d.get('novel_id')}_ep{d.get('episode_num')}"
                if k not in seen_keys:
                    seen_keys.add(k)
                    d_copy = dict(d)
                    d_copy.pop("scenes", None)
                    episodes_list.append(d_copy)
            except Exception:
                continue

        return episodes_list


# Singleton helper
def get_db_manager() -> DatabaseManager:
    return DatabaseManager()

