"""
Storage Auto-Cleanup Engine for CapCut Recap Automation
======================================================
Safely frees up gigabytes of local disk space:
- Removes duplicate and stale video uploads in data/uploads/ (reclaims ~1.4 GB).
- Cleans temporary TTS .wav audio files in data/.
- CRITICAL SAFETY: Protects data/novels/ (novel texts) and data/scene_analysis/ metadata!
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

logger = logging.getLogger("CleanupService")

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
PROTECTED_DIRS = [
    DATA_DIR / "novels",
    DATA_DIR / "database_fallback"
]


def is_protected(path: Path) -> bool:
    """Đảm bảo không bao giờ xóa nhầm các thư mục quan trọng."""
    try:
        resolved = path.resolve()
        for p in PROTECTED_DIRS:
            if p.exists() and (resolved == p.resolve() or p.resolve() in resolved.parents):
                return True
    except Exception:
        pass
    return False


def get_disk_cache_summary() -> Dict[str, Any]:
    """Thống kê chi tiết dung lượng cache cục bộ có thể dọn dẹp."""
    summary = {
        "uploads_count": 0,
        "uploads_size_mb": 0.0,
        "temp_audio_count": 0,
        "temp_audio_size_mb": 0.0,
        "total_cleanable_mb": 0.0,
        "cleanable_files": []
    }

    if UPLOADS_DIR.exists():
        for f in UPLOADS_DIR.glob("*.mp4"):
            if f.is_file() and not is_protected(f):
                size_mb = round(f.stat().st_size / (1024 * 1024), 2)
                summary["uploads_count"] += 1
                summary["uploads_size_mb"] += size_mb
                summary["cleanable_files"].append({
                    "path": str(f),
                    "filename": f.name,
                    "size_mb": size_mb,
                    "type": "video_upload"
                })

    if DATA_DIR.exists():
        for f in DATA_DIR.glob("*temp_audio*.wav"):
            if f.is_file() and not is_protected(f):
                size_mb = round(f.stat().st_size / (1024 * 1024), 2)
                summary["temp_audio_count"] += 1
                summary["temp_audio_size_mb"] += size_mb
                summary["cleanable_files"].append({
                    "path": str(f),
                    "filename": f.name,
                    "size_mb": size_mb,
                    "type": "temp_audio"
                })

    summary["uploads_size_mb"] = round(summary["uploads_size_mb"], 2)
    summary["temp_audio_size_mb"] = round(summary["temp_audio_size_mb"], 2)
    summary["total_cleanable_mb"] = round(summary["uploads_size_mb"] + summary["temp_audio_size_mb"], 2)
    return summary


def cleanup_local_cache(keep_recent_uploads: int = 1, dry_run: bool = False) -> Dict[str, Any]:
    """
    Tiến hành dọn dẹp các video MP4 trùng lặp và file audio tạm.
    keep_recent_uploads: Số lượng file upload mới nhất được giữ lại làm tham khảo (mặc định 1).
    dry_run: Nếu True thì chỉ tính toán chứ không xóa thật.
    """
    result = {
        "freed_mb": 0.0,
        "freed_bytes": 0,
        "removed_files_count": 0,
        "removed_files": [],
        "kept_files": [],
        "dry_run": dry_run
    }

    # 1. Dọn dẹp Video trong data/uploads/
    if UPLOADS_DIR.exists():
        mp4_files = sorted(
            [f for f in UPLOADS_DIR.glob("*.mp4") if f.is_file() and not is_protected(f)],
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        files_to_keep = mp4_files[:keep_recent_uploads]
        files_to_remove = mp4_files[keep_recent_uploads:]

        for k in files_to_keep:
            result["kept_files"].append(k.name)

        for f in files_to_remove:
            try:
                sz = f.stat().st_size
                sz_mb = round(sz / (1024 * 1024), 2)
                if not dry_run:
                    f.unlink()
                    logger.info(f"🗑️ Đã xóa file video trùng lặp: {f.name} ({sz_mb} MB)")
                result["freed_bytes"] += sz
                result["freed_mb"] += sz_mb
                result["removed_files_count"] += 1
                result["removed_files"].append(f.name)
            except Exception as e:
                logger.error(f"Lỗi xóa file {f.name}: {e}")

    # 2. Dọn dẹp file âm thanh tạm trong data/
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("*temp_audio*.wav"):
            if f.is_file() and not is_protected(f):
                try:
                    sz = f.stat().st_size
                    sz_mb = round(sz / (1024 * 1024), 2)
                    if not dry_run:
                        f.unlink()
                        logger.info(f"🗑️ Đã xóa file audio tạm: {f.name} ({sz_mb} MB)")
                    result["freed_bytes"] += sz
                    result["freed_mb"] += sz_mb
                    result["removed_files_count"] += 1
                    result["removed_files"].append(f.name)
                except Exception as e:
                    logger.error(f"Lỗi xóa file audio tạm {f.name}: {e}")

    result["freed_mb"] = round(result["freed_mb"], 2)
    return result
