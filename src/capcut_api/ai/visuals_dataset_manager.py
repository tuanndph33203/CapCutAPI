import os
import sys
import json
import time
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("VisualsDatasetManager")


class VisualsDatasetManager:
    """Quản lý Dataset hình ảnh / video bối cảnh & nhân vật theo từng bộ tiểu thuyết."""

    def __init__(self, base_dir: Optional[Path] = None):
        if base_dir:
            self.dataset_root = Path(base_dir)
        else:
            try:
                from capcut_api.cloud.gdrive_manager import get_gdrive_manager
                self.dataset_root = get_gdrive_manager().get_visuals_dataset_dir()
            except Exception:
                self.dataset_root = Path(__file__).resolve().parent.parent.parent.parent / "data" / "visuals_dataset"
        self.dataset_root.mkdir(parents=True, exist_ok=True)

    def get_novel_visual_dir(self, novel_id: str) -> Path:
        clean_id = "".join(c for c in novel_id if c.isalnum() or c in ("-", "_")).strip() or "default"
        folder = self.dataset_root / clean_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "frames").mkdir(exist_ok=True)
        return folder

    def list_dataset_images(self, novel_id: str) -> List[Dict[str, Any]]:
        folder = self.get_novel_visual_dir(novel_id)
        index_file = folder / "_visuals_index.json"
        
        indexed_items = []
        if index_file.exists():
            try:
                indexed_items = json.loads(index_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        # Scan actual files
        frame_files = sorted(list((folder / "frames").glob("*.jpg")) + list((folder / "frames").glob("*.png")))
        res = []
        existing_filenames = {item["filename"]: item for item in indexed_items if "filename" in item}

        for f in frame_files:
            if f.name in existing_filenames:
                res.append(existing_filenames[f.name])
            else:
                item = {
                    "id": f.stem,
                    "filename": f.name,
                    "path": str(f.resolve()),
                    "novel_id": novel_id,
                    "tags": ["anime", "scene"],
                    "created_at": int(f.stat().st_mtime)
                }
                res.append(item)
        return res

    def extract_frames_from_video(
        self,
        video_path: str,
        novel_id: str,
        interval_seconds: float = 3.0,
        max_frames: int = 60
    ) -> Dict[str, Any]:
        """Tự động trích xuất frame chất lượng cao từ video gốc / trailer bằng FFmpeg."""
        v_path = Path(video_path)
        if not v_path.exists():
            return {"success": False, "error": f"File video không tồn tại: {video_path}"}

        out_dir = self.get_novel_visual_dir(novel_id) / "frames"
        prefix = f"{v_path.stem}_{int(time.time())}"
        
        # FFmpeg command: extract 1 frame every interval_seconds
        fps_filter = f"fps=1/{max(1.0, interval_seconds)}"
        out_pattern = str(out_dir / f"{prefix}_%04d.jpg")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(v_path.resolve()),
            "-vf", fps_filter,
            "-vframes", str(max_frames),
            "-q:v", "2",
            out_pattern
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=120)
        except Exception as e:
            logger.error(f"Lỗi khi chạy ffmpeg extract frames: {e}")
            return {"success": False, "error": str(e)}

        extracted = sorted(list(out_dir.glob(f"{prefix}_*.jpg")))
        
        # Update index
        current_images = self.list_dataset_images(novel_id)
        index_file = self.get_novel_visual_dir(novel_id) / "_visuals_index.json"
        index_file.write_text(json.dumps(current_images, ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "success": True,
            "novel_id": novel_id,
            "extracted_count": len(extracted),
            "frames": [str(p.resolve()) for p in extracted]
        }

    def match_visuals_for_scenes(self, scenes: List[Dict[str, Any]], novel_id: str) -> List[str]:
        """Tự động chọn ảnh khớp nhất từ Dataset cho từng scene trong kịch bản."""
        dataset = self.list_dataset_images(novel_id)
        if not dataset:
            return []

        matched_paths = []
        for idx, sc in enumerate(scenes):
            img_item = dataset[idx % len(dataset)]
            matched_paths.append(img_item["path"])

        return matched_paths
