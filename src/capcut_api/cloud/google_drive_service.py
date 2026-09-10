import os
import sys
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
import httpx

logger = logging.getLogger("GoogleDriveService")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
CONFIG_PATH = ROOT_DIR / "config.json"
DATA_ROOT = ROOT_DIR / "data"

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_BASE = "https://www.googleapis.com/upload/drive/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"


class GoogleDriveService:
    """Quản lý kết nối và upload dữ liệu phân cảnh lên Google Drive thông qua REST API v3."""

    def __init__(self, config_file: Optional[Path] = None):
        self.config_path = config_file or CONFIG_PATH
        self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        self.config: Dict[str, Any] = {}
        if self.config_path.exists():
            try:
                self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"Lỗi đọc config: {e}")
        self.drive_config = self.config.get("google_drive", {})
        return self.drive_config

    def save_config(self, new_config: Dict[str, Any]) -> bool:
        try:
            self._load_config()
            self.config["google_drive"] = new_config
            self.config_path.write_text(
                json.dumps(self.config, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            self.drive_config = new_config
            return True
        except Exception as e:
            logger.error(f"Lỗi lưu Google Drive config: {e}")
            return False

    def get_access_token(self) -> Optional[str]:
        """Lấy access_token còn hạn hoặc tự động refresh nếu có refresh_token."""
        self._load_config()
        cfg = self.drive_config
        access_token = cfg.get("access_token")
        refresh_token = cfg.get("refresh_token")
        client_id = cfg.get("client_id")
        client_secret = cfg.get("client_secret")
        expires_at = cfg.get("expires_at", 0)

        # Nếu token còn hạn hơn 60s, dùng luôn
        if access_token and time.time() < (expires_at - 60):
            return access_token

        # Nếu có refresh token, làm mới
        if refresh_token and client_id and client_secret:
            try:
                logger.info("Đang làm mới Google Drive access_token...")
                payload = {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token"
                }
                res = httpx.post(TOKEN_URL, data=payload, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    new_token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                    cfg["access_token"] = new_token
                    cfg["expires_at"] = int(time.time() + expires_in)
                    self.save_config(cfg)
                    return new_token
                else:
                    logger.error(f"Lỗi refresh token Google Drive: {res.text}")
            except Exception as e:
                logger.error(f"Lỗi kết nối refresh token Google Drive: {e}")

        return access_token

    def test_connection(self) -> Dict[str, Any]:
        """Kiểm tra quyền truy cập Google Drive API."""
        token = self.get_access_token()
        if not token:
            return {
                "success": False,
                "error": "Chưa cấu hình Access Token hoặc Refresh Token của Google Drive!"
            }

        headers = {"Authorization": f"Bearer {token}"}
        try:
            res = httpx.get(
                f"{DRIVE_API_BASE}/about",
                headers=headers,
                params={"fields": "user,storageQuota"},
                timeout=15
            )
            if res.status_code == 200:
                data = res.json()
                return {
                    "success": True,
                    "user": data.get("user", {}),
                    "storage_quota": data.get("storageQuota", {})
                }
            else:
                return {
                    "success": False,
                    "status_code": res.status_code,
                    "error": res.text
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def find_or_create_folder(self, folder_name: str, parent_id: Optional[str] = None) -> Dict[str, Any]:
        """Tìm hoặc tạo thư mục trên Google Drive."""
        token = self.get_access_token()
        if not token:
            return {"success": False, "error": "Chưa xác thực Google Drive."}

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        # 1. Tìm xem thư mục đã tồn tại chưa
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"

        try:
            res = httpx.get(
                f"{DRIVE_API_BASE}/files",
                headers=headers,
                params={"q": query, "fields": "files(id, name, webViewLink)"},
                timeout=15
            )
            if res.status_code == 200:
                files = res.json().get("files", [])
                if files:
                    return {
                        "success": True,
                        "folder_id": files[0]["id"],
                        "folder_name": files[0]["name"],
                        "web_view_link": files[0].get("webViewLink", ""),
                        "already_existed": True
                    }
            
            # 2. Nếu chưa có, tạo mới
            metadata: Dict[str, Any] = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder"
            }
            if parent_id:
                metadata["parents"] = [parent_id]

            create_res = httpx.post(
                f"{DRIVE_API_BASE}/files",
                headers=headers,
                json=metadata,
                params={"fields": "id, name, webViewLink"},
                timeout=15
            )
            if create_res.status_code in (200, 201):
                data = create_res.json()
                return {
                    "success": True,
                    "folder_id": data["id"],
                    "folder_name": data["name"],
                    "web_view_link": data.get("webViewLink", ""),
                    "already_existed": False
                }
            else:
                return {"success": False, "error": f"Lỗi tạo thư mục: {create_res.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def upload_file(
        self,
        file_path: Path,
        parent_folder_id: Optional[str] = None,
        mime_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Tải 1 file lên Google Drive theo chuẩn Multipart Upload."""
        token = self.get_access_token()
        if not token:
            return {"success": False, "error": "Chưa xác thực Google Drive."}

        p = Path(file_path)
        if not p.exists():
            return {"success": False, "error": f"File không tồn tại: {file_path}"}

        if not mime_type:
            suffix = p.suffix.lower()
            if suffix in (".jpg", ".jpeg"):
                mime_type = "image/jpeg"
            elif suffix == ".png":
                mime_type = "image/png"
            elif suffix == ".mp4":
                mime_type = "video/mp4"
            elif suffix == ".json":
                mime_type = "application/json"
            else:
                mime_type = "application/octet-stream"

        headers = {"Authorization": f"Bearer {token}"}
        metadata: Dict[str, Any] = {"name": p.name}
        if parent_folder_id:
            metadata["parents"] = [parent_folder_id]

        try:
            with open(p, "rb") as f:
                file_content = f.read()

            files = {
                "data": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
                "file": (p.name, file_content, mime_type)
            }

            res = httpx.post(
                f"{DRIVE_UPLOAD_BASE}/files?uploadType=multipart&fields=id,name,webViewLink,webContentLink,size",
                headers=headers,
                files=files,
                timeout=120
            )

            if res.status_code in (200, 201):
                data = res.json()
                return {
                    "success": True,
                    "file_id": data.get("id"),
                    "filename": data.get("name"),
                    "web_view_link": data.get("webViewLink"),
                    "size": data.get("size")
                }
            else:
                return {"success": False, "error": f"Lỗi tải file {p.name}: {res.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sync_episode_scenes(
        self,
        novel_id: str,
        novel_name: str,
        episode_num: int,
        sync_keyframes: bool = True,
        sync_clips: bool = False
    ) -> Dict[str, Any]:
        """Tự động đồng bộ toàn bộ ảnh keyframes và phân cảnh của tập phim lên Google Drive."""
        clean_novel_id = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "default"
        ep_dir = DATA_ROOT / "scene_analysis" / clean_novel_id / f"tap_{episode_num}"

        if not ep_dir.exists():
            return {
                "success": False,
                "error": f"Chưa có dữ liệu phân tích phân cảnh cho {novel_name} Tập {episode_num} tại {ep_dir}"
            }

        # 1. Tạo hoặc lấy Root Folder trên Drive
        root_res = self.find_or_create_folder("CapCut_Scenes_Dataset")
        if not root_res.get("success"):
            return root_res
        root_folder_id = root_res["folder_id"]

        # 2. Tạo Folder Bộ Truyện
        novel_res = self.find_or_create_folder(novel_name or novel_id, parent_id=root_folder_id)
        if not novel_res.get("success"):
            return novel_res
        novel_folder_id = novel_res["folder_id"]

        # 3. Tạo Folder Tập Phim
        ep_folder_name = f"Tap_{episode_num}"
        ep_res = self.find_or_create_folder(ep_folder_name, parent_id=novel_folder_id)
        if not ep_res.get("success"):
            return ep_res
        ep_folder_id = ep_res["folder_id"]

        uploaded_files: List[Dict[str, Any]] = []

        # 4. Upload Keyframes
        keyframes_dir = ep_dir / "keyframes"
        if sync_keyframes and keyframes_dir.exists():
            kf_folder_res = self.find_or_create_folder("keyframes", parent_id=ep_folder_id)
            kf_folder_id = kf_folder_res.get("folder_id", ep_folder_id)

            kf_files = sorted(list(keyframes_dir.glob("*.jpg")) + list(keyframes_dir.glob("*.png")))
            for kf in kf_files:
                up_res = self.upload_file(kf, parent_folder_id=kf_folder_id)
                if up_res.get("success"):
                    uploaded_files.append(up_res)

        # 5. Upload Clips (tùy chọn)
        clips_dir = ep_dir / "clips"
        if sync_clips and clips_dir.exists():
            clip_folder_res = self.find_or_create_folder("clips", parent_id=ep_folder_id)
            clip_folder_id = clip_folder_res.get("folder_id", ep_folder_id)

            clip_files = sorted(list(clips_dir.glob("*.mp4")))
            for cl in clip_files:
                up_res = self.upload_file(cl, parent_folder_id=clip_folder_id)
                if up_res.get("success"):
                    uploaded_files.append(up_res)

        # 6. Upload metadata JSON
        meta_file = ep_dir / "scenes_analysis.json"
        if meta_file.exists():
            up_meta = self.upload_file(meta_file, parent_folder_id=ep_folder_id)
            if up_meta.get("success"):
                uploaded_files.append(up_meta)

        # Lưu lại status lên local
        sync_log = {
            "last_synced_at": int(time.time()),
            "drive_folder_id": ep_folder_id,
            "drive_folder_link": ep_res.get("web_view_link", ""),
            "uploaded_count": len(uploaded_files),
            "files": uploaded_files
        }
        (ep_dir / "_drive_sync_status.json").write_text(
            json.dumps(sync_log, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return {
            "success": True,
            "novel_id": novel_id,
            "episode_num": episode_num,
            "drive_folder_id": ep_folder_id,
            "drive_folder_link": ep_res.get("web_view_link", ""),
            "uploaded_count": len(uploaded_files),
            "uploaded_files": uploaded_files
        }
