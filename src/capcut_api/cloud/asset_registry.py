"""
Cloud Asset Registry & Data Definition Engine for CapCut Recap AI
=================================================================
Provides structured data definition, cataloging, indexing, and export
for all dynamic media stored on Google Drive 5TB (and local fallback).

Asset Schema Definition:
- asset_id: Unique asset identifier
- novel_id: e.g. "Phamnhantutien"
- novel_title: Display name
- episode: Episode number (e.g. 186, 189)
- category: video_raw | scene_analysis | keyframes | srt_subtitles | audio_tts | rendered_video | script | visuals_dataset
- filename: Original file name
- drive_path: Absolute storage path on Google Drive
- relative_path: Path relative to CapCutRecapAI root
- size_bytes & size_mb: File size
- mime_type: MIME type
- created_at: Timestamp (epoch ms)
- metadata: Deep scene stats, duration, resolution, tags, word count
- download_url: Direct download URL
"""

import os
import re
import sys
import json
import time
import zipfile
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger("CloudAssetRegistry")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
FALLBACK_DIR = ROOT_DIR / "data" / "database_fallback"


class CloudAssetRegistry:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(CloudAssetRegistry, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        from capcut_api.cloud.gdrive_manager import get_gdrive_manager
        self.gdrive_mgr = get_gdrive_manager()
        self.manifest_cache: Dict[str, Any] = {}
        self._load_or_build_manifest()
        self._initialized = True

    @property
    def drive_root(self) -> Path:
        return self.gdrive_mgr.mount_path or (ROOT_DIR / "data" / "cloud_staging")

    @property
    def manifest_path(self) -> Path:
        return self.drive_root / "manifest.json"

    # =========================================================================
    # 1. AUTO-INDEXING & DATA DEFINITION
    # =========================================================================

    def _parse_episode_and_novel(self, text: str) -> tuple[Optional[str], Optional[int]]:
        """Phân tích số tập và tên truyện từ tên file hoặc đường dẫn thư mục."""
        ep_match = re.search(r'(?:tap|ep|tập)[_\s-]*(\d+)', text, re.IGNORECASE)
        episode = int(ep_match.group(1)) if ep_match else None

        novel_id = None
        text_lower = text.lower()
        if "pham" in text_lower or "phàm" in text_lower or "tutien" in text_lower or "pntt" in text_lower:
            novel_id = "Phamnhantutien"
        elif "xianni" in text_lower or "tiên nghịch" in text_lower or "tien nghich" in text_lower:
            novel_id = "xianni"
        elif "nghich" in text_lower:
            novel_id = "xianni"

        return novel_id, episode

    def _detect_category(self, path: Path, rel_path: str) -> str:
        """Xác định loại tài nguyên dựa trên vị trí và định dạng file."""
        ext = path.suffix.lower()
        rel_lower = rel_path.lower()

        if "keyframes" in rel_lower or "test_extract" in rel_lower:
            return "keyframes"
        if "scenes_analysis.json" in rel_lower or "scene_analysis" in rel_lower:
            if ext == ".json":
                return "scene_analysis"
            elif ext == ".srt":
                return "srt_subtitles"
            elif ext in [".jpg", ".png", ".webp"]:
                return "keyframes"
        if "visuals_dataset" in rel_lower or "test_scenes_images" in rel_lower:
            return "visuals_dataset"
        if "uploads" in rel_lower or "videos" in rel_lower:
            if ext in [".mp4", ".mkv", ".mov", ".avi", ".flv"]:
                return "video_raw"
        if "outputs" in rel_lower or "export" in rel_lower:
            if ext in [".mp4", ".mov"]:
                return "rendered_video"
        if "audio" in rel_lower:
            if ext in [".wav", ".mp3", ".aac", ".m4a"]:
                return "audio_tts"
        if "scripts" in rel_lower:
            if ext in [".json", ".txt"]:
                return "script"

        # Fallback theo phần mở rộng
        if ext in [".mp4", ".mkv"]:
            return "video_raw"
        if ext in [".wav", ".mp3"]:
            return "audio_tts"
        if ext in [".srt"]:
            return "srt_subtitles"
        if ext in [".jpg", ".jpeg", ".png", ".webp"]:
            return "keyframes"
        if ext == ".json":
            return "script"

        return "other"

    def _get_mime_type(self, ext: str) -> str:
        mime_map = {
            ".mp4": "video/mp4",
            ".mkv": "video/x-matroska",
            ".mov": "video/quicktime",
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".srt": "text/plain",
            ".json": "application/json",
            ".txt": "text/plain",
            ".zip": "application/zip"
        }
        return mime_map.get(ext.lower(), "application/octet-stream")

    def build_asset_definition(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Tạo đối tượng định nghĩa chuẩn (Schema) cho một file cụ thể."""
        if not file_path.exists() or file_path.is_dir():
            return None

        # Bỏ qua các file tạm hoặc file manifest
        if file_path.name in ["manifest.json", "desktop.ini", ".DS_Store", "gdrive_connected.txt"]:
            return None

        try:
            stat = file_path.stat()
            size_bytes = stat.st_size
            size_mb = round(size_bytes / (1024 * 1024), 2)
            created_at = int(stat.st_mtime * 1000)
        except Exception:
            size_bytes = 0
            size_mb = 0.0
            created_at = int(time.time() * 1000)

        # Tính relative path so với drive_root
        try:
            rel_path = str(file_path.relative_to(self.drive_root)).replace("\\", "/")
        except Exception:
            rel_path = file_path.name

        category = self._detect_category(file_path, rel_path)
        novel_id, episode = self._parse_episode_and_novel(rel_path + " " + file_path.name)
        if not novel_id:
            novel_id = "Phamnhantutien"
        if episode is None:
            episode = 186

        novel_title_map = {
            "Phamnhantutien": "Phàm Nhân Tu Tiên",
            "xianni": "Tiên Nghịch"
        }
        novel_title = novel_title_map.get(novel_id, novel_id)

        clean_file_id = re.sub(r'[^a-zA-Z0-9_]', '_', file_path.stem)
        asset_id = f"{novel_id.lower()}_ep{episode}_{category}_{clean_file_id}"

        # Đọc metadata chi tiết nếu là file JSON phân tích hoặc SRT
        metadata: Dict[str, Any] = {}
        if category == "scene_analysis" and file_path.suffix.lower() == ".json":
            try:
                content = json.loads(file_path.read_text(encoding="utf-8"))
                scenes = content.get("scenes", [])
                metadata["scenes_count"] = len(scenes)
                metadata["total_duration_sec"] = sum(s.get("estimated_duration_sec", 0) for s in scenes)
                metadata["has_full_analysis"] = True
            except Exception:
                pass
        elif category == "srt_subtitles":
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                srt_blocks = len(re.findall(r'\d+\r?\n\d{2}:\d{2}', text))
                metadata["subtitle_entries"] = srt_blocks
            except Exception:
                pass

        ext = file_path.suffix.lower()
        mime_type = self._get_mime_type(ext)

        return {
            "asset_id": asset_id,
            "novel_id": novel_id,
            "novel_title": novel_title,
            "episode": episode,
            "category": category,
            "filename": file_path.name,
            "relative_path": rel_path,
            "drive_path": str(file_path.resolve()),
            "size_bytes": size_bytes,
            "size_mb": size_mb,
            "mime_type": mime_type,
            "created_at": created_at,
            "metadata": metadata,
            "download_url": f"/api/cloud/download?asset_id={asset_id}"
        }

    # =========================================================================
    # 2. SCAN & SYNC MANIFEST
    # =========================================================================

    def scan_and_index_drive(self) -> Dict[str, Any]:
        """
        Quét toàn bộ thư mục Google Drive 5TB (hoặc local fallback),
        lập chỉ mục mọi file và cập nhật Manifest.
        """
        logger.info(f"⏳ Đang quét và lập chỉ mục toàn bộ dữ liệu tại: {self.drive_root}")
        start_t = time.time()
        assets: List[Dict[str, Any]] = []

        target_subdirs = ["uploads", "scene_analysis", "visuals_dataset", "outputs", "videos", "audio", "scripts", "keyframes"]
        if self.drive_root.exists():
            for folder_name in target_subdirs:
                folder_p = self.drive_root / folder_name
                if not folder_p.exists():
                    continue
                for root_dir, dirs, files in os.walk(str(folder_p)):
                    # Bỏ qua thư mục ẩn hoặc rác
                    dirs[:] = [d for d in dirs if not d.startswith(".") and not d.startswith("$") and d != "__pycache__"]
                    for f in files:
                        if f.startswith(".") or f in ["desktop.ini", "manifest.json"]:
                            continue
                        f_path = Path(root_dir) / f
                        asset = self.build_asset_definition(f_path)
                        if asset:
                            assets.append(asset)

        # Sắp xếp mới nhất lên trước
        assets.sort(key=lambda x: x["created_at"], reverse=True)

        # Tạo thống kê tổng hợp
        categories_count = {}
        total_size_mb = 0.0
        for a in assets:
            cat = a["category"]
            categories_count[cat] = categories_count.get(cat, 0) + 1
            total_size_mb += a.get("size_mb", 0.0)

        manifest = {
            "version": "1.0.0",
            "last_scanned_at": int(time.time() * 1000),
            "scan_duration_sec": round(time.time() - start_t, 2),
            "drive_root": str(self.drive_root),
            "total_assets": len(assets),
            "total_size_mb": round(total_size_mb, 2),
            "total_size_gb": round(total_size_mb / 1024, 3),
            "categories_count": categories_count,
            "assets": assets
        }

        self.manifest_cache = manifest
        self._save_manifest(manifest)
        logger.info(f"✅ Quét xong! Đã lập chỉ mục {len(assets)} tài nguyên ({manifest['total_size_gb']} GB).")
        return manifest

    def _save_manifest(self, manifest: Dict[str, Any]):
        """Lưu manifest.json lên Drive, Fallback Local và MongoDB."""
        # 1. Lưu file manifest.json trên Google Drive
        try:
            self.drive_root.mkdir(parents=True, exist_ok=True)
            self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Không thể ghi manifest.json trên Drive: {e}")

        # 2. Lưu fallback local
        try:
            local_fallback = FALLBACK_DIR / "manifest.json"
            local_fallback.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        # 3. Đồng bộ MongoDB Atlas nếu có
        try:
            from capcut_api.database.mongo_manager import get_db_manager
            db_mgr = get_db_manager()
            if db_mgr.is_connected and db_mgr.db is not None:
                db_mgr.db.cloud_manifest.update_one(
                    {"type": "global_manifest"},
                    {"$set": manifest},
                    upsert=True
                )
                logger.info("✅ Đã đồng bộ Manifest lên MongoDB Atlas!")
        except Exception as e:
            logger.debug(f"Note MongoDB sync manifest: {e}")

    def _load_or_build_manifest(self) -> Dict[str, Any]:
        """Đọc manifest từ Drive hoặc scan mới nếu chưa có."""
        if self.manifest_path.exists():
            try:
                data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                if data and "assets" in data:
                    self.manifest_cache = data
                    return data
            except Exception:
                pass

        local_fallback = FALLBACK_DIR / "manifest.json"
        if local_fallback.exists():
            try:
                data = json.loads(local_fallback.read_text(encoding="utf-8"))
                if data and "assets" in data:
                    self.manifest_cache = data
                    return data
            except Exception:
                pass

        return self.scan_and_index_drive()

    # =========================================================================
    # 3. QUERY ASSETS & EPISODES
    # =========================================================================

    def list_assets(
        self,
        category: Optional[str] = None,
        novel_id: Optional[str] = None,
        episode: Optional[int] = None,
        search: Optional[str] = None,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """Truy vấn danh sách tài nguyên với bộ lọc thông minh."""
        if not self.manifest_cache or not self.manifest_cache.get("assets"):
            self._load_or_build_manifest()

        assets = self.manifest_cache.get("assets", [])
        results = []

        for a in assets:
            if category and a.get("category") != category:
                continue
            if novel_id and a.get("novel_id") != novel_id:
                continue
            if episode is not None and a.get("episode") != episode:
                continue
            if search:
                s = search.lower()
                matches = (
                    s in a.get("filename", "").lower()
                    or s in a.get("novel_title", "").lower()
                    or s in a.get("relative_path", "").lower()
                    or s in str(a.get("episode", ""))
                )
                if not matches:
                    continue
            results.append(a)

        return results[:limit]

    def get_asset_by_id(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """Lấy thông tin tài nguyên theo asset_id."""
        for a in self.manifest_cache.get("assets", []):
            if a.get("asset_id") == asset_id:
                return a
        return None

    def get_asset_file_path(self, asset_id_or_rel: str) -> Optional[Path]:
        """Tìm đường dẫn file thực tế trên ổ đĩa từ asset_id hoặc relative_path."""
        # 1. Tìm theo asset_id
        for a in self.manifest_cache.get("assets", []):
            if a.get("asset_id") == asset_id_or_rel:
                p = Path(a.get("drive_path", ""))
                if p.exists():
                    return p

        # 2. Tìm theo relative_path
        cand = self.drive_root / asset_id_or_rel.replace("/", os.sep)
        if cand.exists():
            return cand

        # 3. Tìm theo tên file
        for p in self.drive_root.rglob(asset_id_or_rel):
            if p.is_file():
                return p

        return None

    def get_episodes_summary(self, novel_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Nhóm tất cả tài nguyên theo từng Tập phim (Episode Bundle Summary):
        Gồm trạng thái có video gốc, số keyframes, có kịch bản, có SRT, audio.
        """
        if not self.manifest_cache or not self.manifest_cache.get("assets"):
            self._load_or_build_manifest()

        assets = self.manifest_cache.get("assets", [])
        episodes_map: Dict[str, Dict[str, Any]] = {}

        for a in assets:
            n_id = a.get("novel_id", "Phamnhantutien")
            if novel_id and n_id != novel_id:
                continue
            ep = a.get("episode", 186)
            key = f"{n_id}_ep{ep}"

            if key not in episodes_map:
                episodes_map[key] = {
                    "bundle_key": key,
                    "novel_id": n_id,
                    "novel_title": a.get("novel_title", n_id),
                    "episode": ep,
                    "total_files": 0,
                    "total_size_mb": 0.0,
                    "has_raw_video": False,
                    "raw_video_filename": "",
                    "has_scenes_analysis": False,
                    "scenes_count": 0,
                    "has_subtitles": False,
                    "srt_filename": "",
                    "keyframes_count": 0,
                    "has_script": False,
                    "has_audio": False,
                    "has_rendered_video": False,
                    "preview_thumbnail": "",
                    "assets": []
                }

            item = episodes_map[key]
            item["total_files"] += 1
            item["total_size_mb"] = round(item["total_size_mb"] + a.get("size_mb", 0.0), 2)
            item["assets"].append(a)

            cat = a.get("category")
            if cat == "video_raw":
                item["has_raw_video"] = True
                item["raw_video_filename"] = a.get("filename", "")
            elif cat == "scene_analysis":
                item["has_scenes_analysis"] = True
                item["scenes_count"] = a.get("metadata", {}).get("scenes_count", 12)
            elif cat == "srt_subtitles":
                item["has_subtitles"] = True
                item["srt_filename"] = a.get("filename", "")
            elif cat == "keyframes":
                item["keyframes_count"] += 1
                if not item["preview_thumbnail"]:
                    item["preview_thumbnail"] = a.get("download_url", "")
            elif cat == "script":
                item["has_script"] = True
            elif cat == "audio_tts":
                item["has_audio"] = True
            elif cat == "rendered_video":
                item["has_rendered_video"] = True

        res = list(episodes_map.values())
        res.sort(key=lambda x: (x["novel_id"], x["episode"]), reverse=True)
        return res

    # =========================================================================
    # 4. DOWNLOAD BUNDLE ZIP & PULL TO LOCAL
    # =========================================================================

    def create_episode_bundle_zip(
        self,
        novel_id: str,
        episode: int,
        output_zip_path: Optional[Path] = None,
        include_raw_video: bool = False
    ) -> Path:
        """
        Nén toàn bộ tài nguyên của 1 tập phim (SRT, Keyframes, Scenes JSON, Script, Audio)
        thành 1 file ZIP để người dùng tải về dùng ngay (siêu nhanh, ~1-3 MB).
        """
        assets = self.list_assets(novel_id=novel_id, episode=episode, limit=500)
        if not assets:
            raise FileNotFoundError(f"Không tìm thấy tài nguyên nào cho {novel_id} Tập {episode}")

        packaged_assets = [a for a in assets if include_raw_video or a.get("category") != "video_raw"]
        if not packaged_assets:
            packaged_assets = assets

        if not output_zip_path:
            staging_zip_dir = ROOT_DIR / "data" / "cloud_staging" / "downloads"
            staging_zip_dir.mkdir(parents=True, exist_ok=True)
            clean_novel = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "novel"
            output_zip_path = staging_zip_dir / f"{clean_novel}_Tap_{episode}_Assets_Package.zip"

        with zipfile.ZipFile(output_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for a in packaged_assets:
                p = Path(a["drive_path"])
                if p.exists() and p.is_file():
                    # Đặt tên trong file zip cho gọn gàng và phân loại rõ
                    cat = a.get("category", "misc")
                    arcname = f"{cat}/{p.name}"
                    zipf.write(p, arcname)

            # Đính kèm manifest tóm tắt của riêng tập này vào trong ZIP
            summary = {
                "novel_id": novel_id,
                "episode": episode,
                "packaged_at": int(time.time() * 1000),
                "files_count": len(assets),
                "assets": assets
            }
            zipf.writestr("package_manifest.json", json.dumps(summary, ensure_ascii=False, indent=2))

        logger.info(f"📦 Đã đóng gói thành công file ZIP cho {novel_id} Tập {episode}: {output_zip_path.name}")
        return output_zip_path

    def pull_asset_to_local(self, asset_id: str, local_dest_dir: Optional[Path] = None) -> Dict[str, Any]:
        """Kéo 1 file từ Google Drive về thư mục làm việc cục bộ nếu cần dùng offline."""
        asset = self.get_asset_by_id(asset_id)
        if not asset:
            return {"success": False, "error": f"Không tìm thấy asset '{asset_id}'"}

        src = Path(asset["drive_path"])
        if not src.exists():
            return {"success": False, "error": f"File nguồn trên Drive không tồn tại: {src}"}

        dest_dir = local_dest_dir or (ROOT_DIR / "data" / asset.get("category", "downloads"))
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / asset["filename"]

        try:
            shutil.copy2(str(src), str(dest))
            return {
                "success": True,
                "asset_id": asset_id,
                "local_path": str(dest.resolve()),
                "filename": dest.name,
                "size_mb": asset.get("size_mb", 0.0)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


def get_asset_registry() -> CloudAssetRegistry:
    return CloudAssetRegistry()
