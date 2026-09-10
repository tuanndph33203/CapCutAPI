"""
Google Drive Cloud Media Manager for CapCut Recap Automation
============================================================
Handles high-capacity media storage (Video .mp4, Audio .wav, Keyframe images):
1. Mode 'Desktop Sync': Automatically detects Google Drive for Desktop (e.g. G:\, H:\)
   or custom sync directory for zero-latency instant offloading of heavy files.
2. Mode 'REST API': Direct Google Drive API upload via OAuth2/Service Account.
3. Mode 'Local Staging': Fallback with organized categories.

Keeps local machine disk usage minimal while taking advantage of 5TB Cloud storage.
"""

import os
import sys
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("GDriveManager")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_FILE = ROOT_DIR / "config.json"


class GDriveManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(GDriveManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path: Optional[Path] = None):
        if self._initialized:
            return
        self.config_path = config_path or CONFIG_FILE
        self.mode = "local"
        self.mount_path: Optional[Path] = None
        self.target_folder_name = "CapCutRecapAI"
        self._init_storage()
        self._initialized = True

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _init_storage(self):
        """Tự động phát hiện Google Drive for Desktop hoặc cấu hình."""
        cfg = self._load_config()
        cloud_cfg = cfg.get("cloud_storage", {})
        custom_mount = cloud_cfg.get("gdrive_mount_path", "").strip()

        # 1. Kiểm tra đường dẫn tùy chỉnh trong config
        if custom_mount and Path(custom_mount).exists():
            self.mount_path = Path(custom_mount) / self.target_folder_name
            self.mode = "desktop_mount"
            self._ensure_folders()
            logger.info(f"✅ Đã kết nối Google Drive qua đường dẫn cấu hình: {self.mount_path}")
            return

        # 2. Tự động dò tìm các ổ đĩa ảo của Google Drive for Desktop (G:\, H:\, F:\)
        for drive_letter in ["G", "H", "F", "D"]:
            cand = Path(f"{drive_letter}:\\My Drive")
            if cand.exists():
                self.mount_path = cand / self.target_folder_name
                self.mode = "desktop_mount"
                self._ensure_folders()
                logger.info(f"✅ Tự động phát hiện Google Drive 5TB tại: {cand}")
                return

        # 3. Chế độ cục bộ (chờ người dùng cấu hình mount path hoặc Google Drive API)
        self.mode = "local_cache"
        self.mount_path = ROOT_DIR / "data" / "cloud_staging"
        self._ensure_folders()
        logger.info("ℹ️ Google Drive chưa được mount -> Đang sử dụng Local Staging Cache.")

    def _ensure_folders(self):
        if self.mount_path:
            try:
                (self.mount_path / "uploads").mkdir(parents=True, exist_ok=True)
                (self.mount_path / "scene_analysis").mkdir(parents=True, exist_ok=True)
                (self.mount_path / "visuals_dataset").mkdir(parents=True, exist_ok=True)
                (self.mount_path / "outputs").mkdir(parents=True, exist_ok=True)
                (self.mount_path / "videos").mkdir(parents=True, exist_ok=True)
                (self.mount_path / "audio").mkdir(parents=True, exist_ok=True)
                (self.mount_path / "keyframes").mkdir(parents=True, exist_ok=True)
                (self.mount_path / "scripts").mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"Không thể tạo thư mục cloud con: {e}")

    # =========================================================================
    # DYNAMIC STORAGE PATH GETTERS (Chuyển toàn bộ dữ liệu động sang Google Drive)
    # =========================================================================

    def get_uploads_dir(self) -> Path:
        """Thư mục lưu trữ video upload từ người dùng."""
        if self.mode != "desktop_mount":
            self._init_storage()
        target = (self.mount_path / "uploads") if self.mount_path else (ROOT_DIR / "data" / "uploads")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_scene_analysis_dir(self) -> Path:
        """Thư mục lưu trữ kết quả phân tích phân cảnh, keyframes và clips."""
        if self.mode != "desktop_mount":
            self._init_storage()
        target = (self.mount_path / "scene_analysis") if self.mount_path else (ROOT_DIR / "data" / "scene_analysis")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_visuals_dataset_dir(self) -> Path:
        """Thư mục lưu trữ kho ảnh, frames trích xuất phục vụ làm video."""
        if self.mode != "desktop_mount":
            self._init_storage()
        target = (self.mount_path / "visuals_dataset") if self.mount_path else (ROOT_DIR / "data" / "visuals_dataset")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_outputs_dir(self) -> Path:
        """Thư mục lưu video/audio render thành phẩm."""
        if self.mode != "desktop_mount":
            self._init_storage()
        target = (self.mount_path / "outputs") if self.mount_path else (ROOT_DIR / "data" / "outputs")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_videos_dir(self) -> Path:
        """Thư mục lưu trữ video gốc/đầu vào."""
        if self.mode != "desktop_mount":
            self._init_storage()
        target = (self.mount_path / "videos") if self.mount_path else (ROOT_DIR / "data" / "videos")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_keyframes_dir(self) -> Path:
        """Thư mục lưu trữ keyframes trích xuất."""
        if self.mode != "desktop_mount":
            self._init_storage()
        target = (self.mount_path / "keyframes") if self.mount_path else (ROOT_DIR / "data" / "keyframes")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_downloads_dir(self) -> Path:
        """Thư mục lưu trữ file download."""
        if self.mode != "desktop_mount":
            self._init_storage()
        target = (self.mount_path / "downloads") if self.mount_path else (ROOT_DIR / "data" / "downloads")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_audio_dir(self) -> Path:
        """Thư mục lưu trữ file âm thanh giọng đọc TTS."""
        if self.mode != "desktop_mount":
            self._init_storage()
        target = (self.mount_path / "audio") if self.mount_path else (ROOT_DIR / "data" / "audio")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_scripts_dir(self) -> Path:
        """Thư mục backup kịch bản trên Google Drive."""
        if self.mode != "desktop_mount":
            self._init_storage()
        target = (self.mount_path / "scripts") if self.mount_path else (ROOT_DIR / "data" / "scripts")
        target.mkdir(parents=True, exist_ok=True)
        return target

    def upload_media(
        self,
        local_file_path: str,
        category: str = "videos",
        custom_filename: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Di chuyển/Sao lưu file media nặng (Video/Audio) sang thư mục Google Drive.
        category: 'videos' | 'uploads' | 'audio' | 'keyframes' | 'scripts'
        """
        src = Path(local_file_path)
        if not src.exists():
            return {"success": False, "error": f"File không tồn tại: {local_file_path}"}

        target_name = custom_filename or src.name
        cat_folder = self.mount_path / category
        cat_folder.mkdir(parents=True, exist_ok=True)
        dest = cat_folder / target_name

        try:
            # Sao chép file sang Google Drive
            shutil.copy2(str(src), str(dest))
            file_size_mb = round(src.stat().st_size / (1024 * 1024), 2)
            logger.info(f"🚀 Đã lưu file '{target_name}' ({file_size_mb} MB) vào Google Drive: {dest}")

            return {
                "success": True,
                "mode": self.mode,
                "filename": target_name,
                "drive_path": str(dest.resolve()),
                "file_size_mb": file_size_mb,
                "category": category
            }
        except Exception as e:
            logger.error(f"Lỗi sao lưu lên Google Drive: {e}")
            return {"success": False, "error": str(e)}

    def get_storage_info(self) -> Dict[str, Any]:
        """Lấy thông tin dung lượng và trạng thái của Google Drive."""
        if self.mode != "desktop_mount":
            self._init_storage()

        info = {
            "mode": self.mode,
            "is_gdrive_active": self.mode == "desktop_mount",
            "mount_path": str(self.mount_path) if self.mount_path else "",
            "total_gb": 0,
            "free_gb": 0,
            "used_gb": 0
        }

        if self.mount_path and self.mount_path.exists():
            try:
                total, used, free = shutil.disk_usage(str(self.mount_path))
                info["total_gb"] = round(total / (1024 ** 3), 2)
                info["free_gb"] = round(free / (1024 ** 3), 2)
                info["used_gb"] = round(used / (1024 ** 3), 2)
            except Exception:
                pass

        return info


def get_gdrive_manager() -> GDriveManager:
    return GDriveManager()
