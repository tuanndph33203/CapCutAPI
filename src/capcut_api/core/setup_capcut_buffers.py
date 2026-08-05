#!/usr/bin/env python3
"""
setup_capcut_buffers.py
-----------------------
Script khoi tao 1 lan de:
  1. Doc danh sach buffer ID tu settings/global_pipeline_settings.json
  2. Tao folder du an trong thu muc CapCut User Data (neu chua co)
  3. Migrate brand overlay snapshot tu ten cu (00000000000, 111111111111111111)
     sang ten moi (capcut_buf_0, capcut_buf_1,...)

Chay: .venv\\Scripts\\python.exe setup_capcut_buffers.py
"""

import os
import sys
import io
import json
import shutil
from pathlib import Path

# Fix Unicode stdout on Windows so Vietnamese/emoji chars don't crash
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent
SETTINGS_PATH = PROJECT_ROOT / "settings" / "global_pipeline_settings.json"
BRAND_OVERLAYS_DIR = PROJECT_ROOT / "brand_overlays"

DEFAULT_CAPCUT_DRAFTS = Path(os.environ.get("LOCALAPPDATA", ""), "CapCut", "User Data", "Projects", "com.lveditor.draft")
OLD_BUFFER_IDS = ["00000000000", "111111111111111111"]


def load_buffer_ids() -> list:
    """Đọc danh sách buffer ID mới từ config."""
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        buffers = data.get("capcut_draft_buffers")
        if isinstance(buffers, list) and buffers:
            return [str(b) for b in buffers if b]
    except Exception as e:
        print(f"[WARN] Không đọc được settings: {e}")
    return []


def get_capcut_drafts_dir() -> Path:
    """Lấy đường dẫn thư mục CapCut drafts, hỗ trợ override qua env."""
    env_override = os.environ.get("CAPCUT_DRAFTS_DIR", "")
    if env_override:
        return Path(env_override)
    return DEFAULT_CAPCUT_DRAFTS


def create_draft_folder(capcut_drafts: Path, draft_id: str) -> bool:
    """Tạo folder dự án trong CapCut User Data nếu chưa tồn tại."""
    folder = capcut_drafts / draft_id
    if folder.exists():
        print(f"  [OK] Folder đã tồn tại: {folder}")
        return False
    try:
        folder.mkdir(parents=True, exist_ok=True)
        # Tạo file draft_info.json tối thiểu để CapCut nhận ra đây là dự án hợp lệ
        draft_info = {
            "draft_id": draft_id,
            "draft_name": draft_id,
            "draft_type": 0,
            "tm_draft_create": 0,
            "tm_draft_modified": 0,
        }
        (folder / "draft_info.json").write_text(
            json.dumps(draft_info, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        print(f"  [CREATED] Tạo folder mới: {folder}")
        return True
    except Exception as e:
        print(f"  [ERROR] Không thể tạo folder {folder}: {e}")
        return False


def migrate_brand_overlay(old_id: str, new_id: str) -> bool:
    """
    Copy brand overlay snapshot từ tên buffer cũ sang tên mới.
    Chỉ copy nếu file cũ tồn tại và file mới chưa có.
    """
    old_file = BRAND_OVERLAYS_DIR / f"{old_id}.json"
    new_file = BRAND_OVERLAYS_DIR / f"{new_id}.json"

    if not old_file.exists():
        print(f"  [SKIP] Brand overlay cũ không tồn tại: {old_file.name}")
        return False
    if new_file.exists():
        print(f"  [SKIP] Brand overlay mới đã tồn tại: {new_file.name}")
        return False

    try:
        # Đọc nội dung cũ, cập nhật trường 'source' (nếu có) sang tên mới
        data = json.loads(old_file.read_text(encoding="utf-8"))
        source = data.get("source", "")
        if old_id in source:
            data["source"] = source.replace(old_id, new_id)
        BRAND_OVERLAYS_DIR.mkdir(parents=True, exist_ok=True)
        new_file.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        print(f"  [MIGRATED] {old_file.name} → {new_file.name}")
        return True
    except Exception as e:
        print(f"  [ERROR] Không thể migrate brand overlay: {e}")
        return False


def main():
    print("=" * 60)
    print("CapCut Buffer Setup")
    print("=" * 60)

    # 1. Đọc buffer IDs mới
    new_ids = load_buffer_ids()
    if not new_ids:
        print("[ERROR] Không tìm thấy 'capcut_draft_buffers' trong settings.")
        print(f"  Hãy thêm vào {SETTINGS_PATH}")
        return 1

    print(f"\nBuffer IDs mới: {new_ids}")

    # 2. Xác định thư mục CapCut
    capcut_drafts = get_capcut_drafts_dir()
    print(f"CapCut drafts dir: {capcut_drafts}")
    if not capcut_drafts.exists():
        print(f"[WARN] Thư mục CapCut không tồn tại: {capcut_drafts}")
        print("  Pipeline vẫn sẽ tạo folder khi cần, nhưng CapCut có thể không nhận ra dự án.")

    # 3. Tạo folder dự án trong CapCut
    print("\n--- Tạo folder dự án CapCut ---")
    for draft_id in new_ids:
        create_draft_folder(capcut_drafts, draft_id)

    # 4. Migrate brand overlay snapshots
    print("\n--- Migrate Brand Overlay Snapshots ---")
    for i, new_id in enumerate(new_ids):
        old_id = OLD_BUFFER_IDS[i] if i < len(OLD_BUFFER_IDS) else None
        if old_id:
            print(f"  Buffer {i}: {old_id} → {new_id}")
            migrate_brand_overlay(old_id, new_id)
        else:
            print(f"  Buffer {i}: {new_id} (không có buffer cũ tương ứng để migrate)")

    # 5. Hướng dẫn tiếp theo
    print("\n" + "=" * 60)
    print("Hoàn tất! Các bước tiếp theo:")
    print("=" * 60)
    print("\n1. Mở CapCut -> vào phần 'Dự án' (Projects)")
    print("   Các dự án sau sẽ xuất hiện trong danh sách:")
    for draft_id in new_ids:
        folder = capcut_drafts / draft_id
        print(f"     - {draft_id}  ({folder})")
    print("\n2. Nếu muốn đặt brand overlay (logo/watermark) cho từng buffer:")
    print("   a. Mở từng dự án trong CapCut")
    print("   b. Thêm GIF/ảnh logo vào timeline dự án")
    print("   c. Chạy lại pipeline 1 lần để tự động capture snapshot brand overlay")
    print("\n3. Pipeline sẽ tự động dùng tên buffer mới từ bây giờ.")
    print("   Cấu hình tại: settings/global_pipeline_settings.json")
    print("   Key: capcut_draft_buffers")

    return 0


if __name__ == "__main__":
    exit(main())
