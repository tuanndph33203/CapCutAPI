import os
import sys
import re
import json
import uuid
import time
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from openai import OpenAI
import edge_tts
import requests
from bs4 import BeautifulSoup
from capcut_api.ai.visuals_dataset_manager import VisualsDatasetManager
import logging

logger = logging.getLogger("novel_recap_engine")

_CN_MAP = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100, '千': 1000, '万': 10000}
_CH_DIGITS = r'一二两三四五六七八九十百千万零0-9\d'

def parse_cn_number(s: str) -> Optional[int]:
    """Chuyển đổi số tiếng Trung hoặc chữ số thường thành số nguyên."""
    if not s:
        return None
    s = s.strip()
    if s.isdigit():
        return int(s)
    res, temp = 0, 0
    for ch in s:
        if ch not in _CN_MAP:
            continue
        v = _CN_MAP[ch]
        if v >= 10:
            if temp == 0:
                temp = 1
            res += temp * v
            temp = 0
        else:
            temp = v
    res += temp
    return res if res > 0 else None

class SmartNovelChapterSplitter:
    """
    Trình phân tích & chia tách chương tiểu thuyết thông minh:
    - Nhận diện tất cả các định dạng tiêu đề (Tiếng Trung, Tiếng Việt, Tiếng Anh)
    - Trích xuất số chương chính xác (kể cả số chữ Hán như '两千一百六十三')
    - Đặt tên file chuẩn hóa có thứ tự: ch_02163_第2163章_木族大战.md
    - Tạo bộ Search Keys phong phú phục vụ tìm kiếm & khớp nối Whisper AI
    - Tự động sinh file index _chapters_index.json
    """
    CH_HEADER_REGEX = re.compile(
        r'(?:^|\n)[ \t　]*(?:[\-\*_=\s\n]{0,30})?(?:[#\*\-]+\s*)?'
        r'(?:(?:第[' + _CH_DIGITS + r']+卷[^\n]{0,40}\s+)?'
        r'(?:(?:\d+[\.\s]+)?[第\s]*([' + _CH_DIGITS + r']+)[\s]*[章回节](?:[\s\(（]\d+[）\)])?|(?<!\w)([' + _CH_DIGITS + r']+)[\s]*章)'
        r'|(?:(?:Quyển|Tập|Vol)\s*[' + _CH_DIGITS + r']+[^\n]{0,40}\s+)?(?:Chương|Hồi|Chapter|Chap)\s*([' + _CH_DIGITS + r']+))'
        r'[：:\s\.\-]*([^\n]{0,80})',
        re.IGNORECASE
    )

    @classmethod
    def split_and_index_novel(cls, raw_text: str, target_dir: Path) -> List[Dict[str, Any]]:
        target_dir.mkdir(parents=True, exist_ok=True)
        # Xóa các file cũ nếu có
        for old_f in target_dir.glob("*.md"):
            try:
                old_f.unlink()
            except Exception:
                pass

        raw_matches = list(cls.CH_HEADER_REGEX.finditer(raw_text))
        # Loại bỏ các match trùng lặp quá gần nhau (dưới 80 ký tự)
        matches = []
        last_pos = -9999
        for m in raw_matches:
            if m.start() - last_pos > 80:
                matches.append(m)
                last_pos = m.start()

        chapters_data = []

        if len(matches) > 1:
            for i, m in enumerate(matches):
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(raw_text)
                
                raw_num_str = m.group(1) or m.group(2) or m.group(3)
                ch_num = parse_cn_number(raw_num_str) if raw_num_str else (i + 1)
                if ch_num is None or ch_num <= 0:
                    ch_num = i + 1
                    
                raw_title_suffix = (m.group(4) or "").strip()
                # Làm sạch tiêu đề, bỏ các ký tự phân cách gạch ngang, markdown header
                header_line = re.sub(r'^[\s\n\-\*_=#]+', '', m.group(0)).strip()
                header_line = re.sub(r'[\s\n]+', ' ', header_line)
                clean_title = header_line[:60].strip()
                if not clean_title:
                    clean_title = f"Chương {ch_num}: {raw_title_suffix}"

                content = raw_text[start:end].strip()
                
                # Tạo search keys phong phú
                search_keys = [
                    str(ch_num),
                    f"Chương {ch_num}",
                    f"chuong {ch_num}",
                    f"Chapter {ch_num}",
                    f"第{ch_num}章",
                    f"ch_{ch_num:04d}",
                    clean_title
                ]
                if raw_title_suffix:
                    search_keys.append(raw_title_suffix)

                safe_title_part = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fa5\u00C0-\u1EF9]', '_', clean_title)[:25]
                filename = f"ch_{ch_num:05d}_{safe_title_part}.md"
                file_path = target_dir / filename
                file_path.write_text(f"# {clean_title}\n\n{content}", encoding="utf-8")

                chapters_data.append({
                    "index": i + 1,
                    "chapter_num": ch_num,
                    "title": clean_title,
                    "filename": filename,
                    "search_keys": list(set(search_keys)),
                    "size_kb": round(len(content.encode("utf-8")) / 1024, 1),
                    "word_count": len(content.split())
                })
        else:
            # Fallback: Nếu không phát hiện header, chia theo đoạn 2500 từ
            lines = raw_text.splitlines()
            chunk_lines = 60
            for idx, i in enumerate(range(0, len(lines), chunk_lines)):
                ch_num = idx + 1
                title = f"Chương {ch_num}"
                content = "\n".join(lines[i:i+chunk_lines])
                filename = f"ch_{ch_num:05d}_Chuong_{ch_num}.md"
                file_path = target_dir / filename
                file_path.write_text(f"# {title}\n\n{content}", encoding="utf-8")

                chapters_data.append({
                    "index": idx + 1,
                    "chapter_num": ch_num,
                    "title": title,
                    "filename": filename,
                    "search_keys": [str(ch_num), f"Chương {ch_num}", f"Chapter {ch_num}"],
                    "size_kb": round(len(content.encode("utf-8")) / 1024, 1),
                    "word_count": len(content.split())
                })

        # Lưu file index JSON
        index_file = target_dir / "_chapters_index.json"
        index_file.write_text(json.dumps(chapters_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return chapters_data


class NovelRepositoryManager:
    """
    Quản lý Kho Tiểu Thuyết & Nhập Truyện Đa Nguồn:
    - Nhập từ thư mục (.txt, .md) trên máy tính
    - Nhập từ file text dài / Paste nội dung raw (tự động cắt chương thông minh)
    - Nhập từ Link web truyện (Crawl)
    """
    def __init__(self):
        self.root_dir = Path(__file__).resolve().parent.parent.parent.parent
        self.harness_novels_dir = self.root_dir.parent / "harnessNovel" / "my-novels"
        self.custom_novels_dir = self.root_dir / "data" / "novels"
        self.custom_novels_dir.mkdir(parents=True, exist_ok=True)

    def list_all_novels(self) -> List[Dict[str, Any]]:
        novels = []
        
        # 1. Scan harnessNovel/my-novels
        if self.harness_novels_dir.exists():
            for p in self.harness_novels_dir.iterdir():
                if p.is_dir():
                    ch_dir = p / "reference" / "chapters"
                    if not ch_dir.exists():
                        ch_dir = p
                    ch_files = [f for f in list(ch_dir.glob("**/*.md")) + list(ch_dir.glob("**/*.txt")) if not f.name.startswith("_")]
                    display_name = "Tiên Nghịch (仙逆 - Nhĩ Căn)" if p.name == "仙逆" else p.name
                    novels.append({
                        "id": p.name,
                        "name": display_name,
                        "chapters_count": len(ch_files),
                        "path": str(ch_dir.resolve()),
                        "source": "harness_novel"
                    })

        # 2. Scan custom imported novels in data/novels
        if self.custom_novels_dir.exists():
            for p in self.custom_novels_dir.iterdir():
                if p.is_dir():
                    ch_dir = p / "chapters"
                    if not ch_dir.exists():
                        ch_dir = p
                    ch_files = [f for f in list(ch_dir.glob("**/*.md")) + list(ch_dir.glob("**/*.txt")) if not f.name.startswith("_")]
                    novels.append({
                        "id": p.name,
                        "name": p.name,
                        "chapters_count": len(ch_files),
                        "path": str(ch_dir.resolve()),
                        "source": "imported"
                    })

        # Đảm bảo Tiên Nghịch luôn có mặt nếu chưa scan được
        if not any(n["id"] in ("仙逆", "xianni", "Tien_Nghich") for n in novels):
            novels.insert(0, {
                "id": "xianni",
                "name": "Tiên Nghịch (仙逆 - Nhĩ Căn)",
                "chapters_count": 2073,
                "path": str((self.harness_novels_dir / "仙逆" / "reference" / "chapters").resolve()),
                "source": "builtin"
            })
            
        return novels

    def import_from_folder(self, novel_name: str, source_folder: str) -> Dict[str, Any]:
        src = Path(source_folder)
        if not src.exists() or not src.is_dir():
            raise ValueError(f"Thư mục không tồn tại: {source_folder}")

        clean_name = re.sub(r'[^\w\-_\. ]', '_', novel_name).strip() or "Novel_Imported"
        target_dir = self.custom_novels_dir / clean_name / "chapters"
        target_dir.mkdir(parents=True, exist_ok=True)

        files = list(src.glob("**/*.txt")) + list(src.glob("**/*.md"))
        if len(files) == 1:
            # 1 file lớn trong folder -> phân tách chương thông minh
            raw_text = files[0].read_text(encoding="utf-8", errors="ignore")
            chapters_data = SmartNovelChapterSplitter.split_and_index_novel(raw_text, target_dir)
            return {
                "success": True,
                "novel_id": clean_name,
                "novel_name": novel_name,
                "chapters_count": len(chapters_data),
                "target_dir": str(target_dir.resolve())
            }
        else:
            copied = 0
            for f in sorted(files):
                if f.name.startswith("_"):
                    continue
                dest = target_dir / f.name
                shutil.copy2(f, dest)
                copied += 1

            return {
                "success": True,
                "novel_id": clean_name,
                "novel_name": novel_name,
                "chapters_count": copied,
                "target_dir": str(target_dir.resolve())
            }

    def import_from_text(self, novel_name: str, raw_text: str) -> Dict[str, Any]:
        clean_name = re.sub(r'[^\w\-_\. ]', '_', novel_name).strip() or "Novel_Imported"
        target_dir = self.custom_novels_dir / clean_name / "chapters"
        target_dir.mkdir(parents=True, exist_ok=True)

        chapters_data = SmartNovelChapterSplitter.split_and_index_novel(raw_text, target_dir)

        return {
            "success": True,
            "novel_id": clean_name,
            "novel_name": novel_name,
            "chapters_count": len(chapters_data),
            "target_dir": str(target_dir.resolve())
        }

    def _get_novel_path(self, novel_id: str) -> Path:
        novel_id_str = str(novel_id).strip()

        # 1. Alias cho Tiên Nghịch
        if novel_id_str in ("xianni", "仙逆", "Tien_Nghich", "Tiên Nghịch"):
            p = self.harness_novels_dir / "仙逆" / "reference" / "chapters"
            if p.exists() and len(list(p.glob("**/*"))) > 0:
                return p

        # 2. Alias cho Phàm Nhân Tu Tiên
        if any(k in novel_id_str.lower() for k in ["pham", "nhan", "tu", "tien"]):
            p = self.custom_novels_dir / "Pham nhan tu tien" / "chapters"
            if p.exists():
                return p

        # 3. Check custom_novels_dir (chỉ lấy nếu có file chương)
        target = self.custom_novels_dir / novel_id_str
        if target.exists() and target.is_dir():
            ch_dir = target / "chapters"
            if ch_dir.exists() and any(ch_dir.glob("**/*.txt")):
                return ch_dir
            if any(target.glob("**/*.txt")) or any(target.glob("**/*.md")):
                return target
            
        # 4. Check harness_novels_dir
        target_harness = self.harness_novels_dir / novel_id_str
        if target_harness.exists() and target_harness.is_dir():
            ch_dir = target_harness / "reference" / "chapters"
            if ch_dir.exists() and (any(ch_dir.glob("**/*.txt")) or any(ch_dir.glob("**/*.md"))):
                return ch_dir
            if any(target_harness.glob("**/*.txt")) or any(target_harness.glob("**/*.md")):
                return target_harness

        # 5. Duyệt tìm bất kỳ thư mục nào có chương
        all_dirs = []
        if self.custom_novels_dir.exists():
            all_dirs.extend([p for p in self.custom_novels_dir.iterdir() if p.is_dir()])
        if self.harness_novels_dir.exists():
            all_dirs.extend([p for p in self.harness_novels_dir.iterdir() if p.is_dir()])

        for p in all_dirs:
            if p.name.lower() == novel_id_str.lower() or novel_id_str.lower() in p.name.lower():
                ch_dir = p / "chapters"
                if ch_dir.exists() and any(ch_dir.glob("**/*.txt")):
                    return ch_dir
                ch_ref = p / "reference" / "chapters"
                if ch_ref.exists() and any(ch_ref.glob("**/*")):
                    return ch_ref
                if any(p.glob("**/*.txt")) or any(p.glob("**/*.md")):
                    return p

        # Fallback cuối cùng: nếu không tìm thấy gì, trả về Pham nhan tu tien nếu có
        p_pntt = self.custom_novels_dir / "Pham nhan tu tien" / "chapters"
        if p_pntt.exists():
            return p_pntt

        raise ValueError(f"Không tìm thấy thư mục của bộ truyện '{novel_id}'.")

    def list_novel_chapters(self, novel_id: str) -> List[Dict[str, Any]]:
        """Lấy danh sách toàn bộ các file chương của 1 bộ truyện kèm Search Keys."""
        ch_dir = self._get_novel_path(novel_id)
        
        # 1. Kiểm tra nếu có file index json đã sinh
        index_file = ch_dir / "_chapters_index.json"
        if index_file.exists():
            try:
                data = json.loads(index_file.read_text(encoding="utf-8"))
                if isinstance(data, list) and len(data) > 0:
                    return data
            except Exception:
                pass

        # 2. Quét các file chương thông thường
        files = sorted(
            [f for f in list(ch_dir.glob("**/*.md")) + list(ch_dir.glob("**/*.txt")) if not f.name.startswith("_")],
            key=lambda x: x.name
        )
        
        result = []
        for idx, f in enumerate(files):
            # Trích xuất số chương từ tên file
            num_match = re.search(r'(\d+)', f.stem)
            ch_num = int(num_match.group(1)) if num_match else (idx + 1)
            
            clean_title = f.stem.replace('_', ' ').strip()
            search_keys = [
                str(ch_num),
                f"Chương {ch_num}",
                f"Chapter {ch_num}",
                f"第{ch_num}章",
                clean_title
            ]

            result.append({
                "index": idx + 1,
                "chapter_num": ch_num,
                "filename": f.name,
                "title": clean_title,
                "search_keys": search_keys,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "modified_time": int(f.stat().st_mtime * 1000)
            })
        return result

    def resplit_novel_chapters(self, novel_id: str) -> Dict[str, Any]:
        """Tách lại toàn bộ chương từ file lớn và tái tạo Search Keys chuẩn."""
        ch_dir = self._get_novel_path(novel_id)
        files = [f for f in list(ch_dir.glob("**/*.md")) + list(ch_dir.glob("**/*.txt")) if not f.name.startswith("_")]
        if not files:
            raise ValueError(f"Không có file nào trong thư mục của bộ truyện '{novel_id}'.")

        # Gom toàn bộ nội dung
        full_text = "\n\n".join([f.read_text(encoding="utf-8", errors="ignore") for f in files])
        chapters_data = SmartNovelChapterSplitter.split_and_index_novel(full_text, ch_dir)
        return {
            "success": True,
            "novel_id": novel_id,
            "chapters_count": len(chapters_data),
            "message": f"Đã chia tách và lập chỉ mục {len(chapters_data)} chương thành công!"
        }

    def get_chapter_content(self, novel_id: str, filename: str) -> Dict[str, Any]:
        """Đọc nội dung văn bản của 1 chương cụ thể."""
        ch_dir = self._get_novel_path(novel_id)
        file_path = ch_dir / filename
        if not file_path.exists():
            for f in ch_dir.glob("**/*"):
                if f.name == filename:
                    file_path = f
                    break
        if not file_path.exists():
            raise ValueError(f"Không tìm thấy file chương '{filename}'.")

        content = file_path.read_text(encoding="utf-8", errors="ignore")
        return {
            "success": True,
            "novel_id": novel_id,
            "filename": filename,
            "title": file_path.stem,
            "content": content
        }

    def save_chapter_content(self, novel_id: str, filename: str, content: str) -> Dict[str, Any]:
        """Lưu nội dung văn bản đã chỉnh sửa của chương."""
        ch_dir = self._get_novel_path(novel_id)
        file_path = ch_dir / filename
        if not file_path.exists():
            for f in ch_dir.glob("**/*"):
                if f.name == filename:
                    file_path = f
                    break
        file_path.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "novel_id": novel_id,
            "filename": filename,
            "size_bytes": len(content.encode("utf-8")),
            "message": "Đã lưu nội dung chương thành công!"
        }

    def rename_novel(self, novel_id: str, new_name: str) -> Dict[str, Any]:
        """Đổi tên bộ truyện."""
        clean_new = re.sub(r'[^\w\-_\. ]', '_', new_name).strip()
        target = self.custom_novels_dir / novel_id
        if target.exists() and target.is_dir():
            new_target = self.custom_novels_dir / clean_new
            if target.resolve() != new_target.resolve():
                target.rename(new_target)
            return {"success": True, "old_id": novel_id, "new_id": clean_new, "new_name": new_name}
        return {"success": True, "novel_id": novel_id, "new_name": new_name}

    def delete_novel(self, novel_id: str) -> Dict[str, Any]:
        """Xóa bộ truyện khỏi danh sách."""
        deleted = False
        target = self.custom_novels_dir / novel_id
        if target.exists() and target.is_dir():
            shutil.rmtree(target)
            deleted = True
            
        target_harness = self.harness_novels_dir / novel_id
        if target_harness.exists() and target_harness.is_dir():
            shutil.rmtree(target_harness)
            deleted = True

        if not deleted:
            raise ValueError(f"Không tìm thấy bộ truyện '{novel_id}' để xóa.")

        return {"success": True, "novel_id": novel_id, "message": f"Đã xóa thành công bộ truyện '{novel_id}'."}

    def import_from_uploaded_files(self, novel_name: str, files: List[Any]) -> Dict[str, Any]:
        """
        Nhập truyện từ danh sách 1 hoặc nhiều file upload (.txt, .md).
        - Nếu 1 file: tự động nhận diện chia tách các chương.
        - Nếu nhiều file: mỗi file là 1 chương, tự động sắp xếp theo thứ tự.
        """
        clean_name = re.sub(r'[^\w\-_\. ]', '_', novel_name).strip() or "Novel_Imported"
        target_dir = self.custom_novels_dir / clean_name / "chapters"
        target_dir.mkdir(parents=True, exist_ok=True)

        total_saved = 0
        if len(files) == 1:
            # 1 file duy nhất -> đọc text và chia chương
            f = files[0]
            content = f.get("content", "") or ""
            return self.import_from_text(novel_name, content)
        else:
            # Nhiều file (mỗi file 1 chương)
            for idx, file_obj in enumerate(files):
                filename = file_obj.get("filename", f"Chương_{idx+1}.md")
                content = file_obj.get("content", "")
                safe_name = f"{idx+1:04d}_{re.sub(r'[^a-zA-Z0-9_.]', '_', filename)}"
                if not safe_name.endswith(('.md', '.txt')):
                    safe_name += '.md'
                (target_dir / safe_name).write_text(content, encoding="utf-8")
                total_saved += 1

        return {
            "success": True,
            "novel_id": clean_name,
            "novel_name": novel_name,
            "chapters_count": total_saved,
            "target_dir": str(target_dir.resolve())
        }

    def list_novel_scripts(self, novel_id: str) -> List[Dict[str, Any]]:
        """Lấy danh sách các kịch bản review / thuyết minh của bộ truyện."""
        scripts_dir = self.custom_novels_dir / novel_id / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        
        # Cũng quét các file kịch bản trong thư mục gốc của novel (ví dụ: tap_186_master_review.txt)
        novel_dir = self.custom_novels_dir / novel_id
        all_files = list(scripts_dir.glob("*.txt")) + list(scripts_dir.glob("*.srt"))
        if novel_dir.exists():
            for f in novel_dir.glob("tap_*.txt"):
                if f not in all_files:
                    all_files.append(f)
                    
        # Cũng quét trong Downloads nếu có file liên quan tới novel này
        user_dl = Path(os.environ.get("USERPROFILE", r"C:\Users\admin.TRANANH")) / "Downloads"
        if user_dl.exists():
            for f in user_dl.glob("*.srt"):
                if "Phàm Nhân" in f.name or "Phạm Dân" in f.name or "Tiên Nghịch" in f.name:
                    all_files.append(f)

        results = []
        for idx, f in enumerate(sorted(all_files, key=lambda x: x.stat().st_mtime, reverse=True)):
            ep_match = re.search(r'(?:tập|tap|ep|episode|_|\s)(\d{1,4})', f.name, re.IGNORECASE)
            ep_num = int(ep_match.group(1)) if ep_match else None
            results.append({
                "id": f.name,
                "name": f.name,
                "episode": ep_num,
                "path": str(f.resolve()),
                "size_kb": round(f.stat().st_size / 1024, 1),
                "modified_time": int(f.stat().st_mtime * 1000),
                "is_download": str(user_dl.resolve()) in str(f.resolve())
            })
        return results

    def get_novel_script_content(self, novel_id: str, script_name: str) -> Dict[str, Any]:
        """Đọc nội dung kịch bản."""
        scripts_dir = self.custom_novels_dir / novel_id / "scripts"
        novel_dir = self.custom_novels_dir / novel_id
        user_dl = Path(os.environ.get("USERPROFILE", r"C:\Users\admin.TRANANH")) / "Downloads"

        target_file = None
        for cand in [scripts_dir / script_name, novel_dir / script_name, user_dl / script_name]:
            if cand.exists():
                target_file = cand
                break

        if not target_file:
            raise ValueError(f"Không tìm thấy file kịch bản '{script_name}'.")

        content = target_file.read_text(encoding="utf-8", errors="ignore")
        return {
            "success": True,
            "name": script_name,
            "path": str(target_file.resolve()),
            "content": content
        }

    def save_novel_script_content(self, novel_id: str, script_name: str, content: str) -> Dict[str, Any]:
        """Lưu nội dung kịch bản."""
        scripts_dir = self.custom_novels_dir / novel_id / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        
        if not script_name.endswith(('.txt', '.srt')):
            script_name += '.txt'
            
        target_file = scripts_dir / script_name
        target_file.write_text(content, encoding="utf-8")
        return {
            "success": True,
            "name": script_name,
            "path": str(target_file.resolve()),
            "size_kb": round(len(content.encode('utf-8')) / 1024, 1),
            "message": f"Đã lưu kịch bản '{script_name}' thành công!"
        }

    def delete_novel_script(self, novel_id: str, script_name: str) -> Dict[str, Any]:
        """Xóa file kịch bản."""
        scripts_dir = self.custom_novels_dir / novel_id / "scripts"
        novel_dir = self.custom_novels_dir / novel_id
        
        deleted = False
        for cand in [scripts_dir / script_name, novel_dir / script_name]:
            if cand.exists():
                cand.unlink()
                deleted = True
                break
        if not deleted:
            raise ValueError(f"Không tìm thấy kịch bản '{script_name}' để xóa.")
        return {"success": True, "name": script_name, "message": f"Đã xóa kịch bản '{script_name}'."}

    def import_from_url(self, novel_name: str, url: str) -> Dict[str, Any]:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        res = requests.get(url, headers=headers, timeout=15)
        res.encoding = res.apparent_encoding or "utf-8"
        
        soup = BeautifulSoup(res.text, "html.parser")
        # Tìm tiêu đề và nội dung chính
        title = soup.find(["h1", "h2", "title"])
        novel_title = novel_name or (title.get_text().strip() if title else "Novel_Web")
        
        # Bóc tách text các đoạn
        paragraphs = [p.get_text().strip() for p in soup.find_all(["p", "div"]) if len(p.get_text().strip()) > 40]
        raw_text = "\n\n".join(paragraphs)
        
        return self.import_from_text(novel_title, raw_text)


class NovelVideoPipelineService:
    """
    Dịch vụ Tích Hợp Trực Tiếp trong CapCutAPI:
    - Đọc kho tiểu thuyết (Tiên Nghịch hoặc truyện đã import)
    - Biên kịch Thuyết minh / Spoiler trước tập sau
    - Lồng tiếng AI (Edge-TTS siêu nhẹ)
    - Tự động tạo Project CapCut Draft (Ảnh + Subtitle + Voiceover)
    """
    def __init__(self, novel_id: Optional[str] = None, chapters_dir: Optional[str] = None):
        self.root_dir = Path(__file__).resolve().parent.parent.parent.parent
        self.repo = NovelRepositoryManager()
        self.visuals_mgr = VisualsDatasetManager(self.root_dir / "data" / "visuals_dataset")
        self.novel_id = novel_id or "Pham nhan tu tien"
        
        if chapters_dir:
            self.chapters_dir = Path(chapters_dir)
        elif novel_id:
            all_novels = self.repo.list_all_novels()
            matched = next((n for n in all_novels if n["id"] == novel_id), None)
            if matched:
                self.chapters_dir = Path(matched["path"])
            else:
                self.chapters_dir = self.root_dir.parent / "harnessNovel" / "my-novels" / "仙逆" / "reference" / "chapters"
        else:
            self.chapters_dir = self.root_dir.parent / "harnessNovel" / "my-novels" / "仙逆" / "reference" / "chapters"
        
        # Mặc định CapCut Projects folder
        local_appdata = os.environ.get("LOCALAPPDATA", r"C:\Users\admin.TRANANH\AppData\Local")
        self.capcut_drafts_dir = Path(local_appdata) / "CapCut" / "User Data" / "Projects" / "com.lveditor.draft"
        self.capcut_drafts_dir.mkdir(parents=True, exist_ok=True)

        try:
            from capcut_api.cloud.gdrive_manager import get_gdrive_manager
            self.audio_output_dir = get_gdrive_manager().get_outputs_dir() / "novel_audio"
        except Exception:
            self.audio_output_dir = self.root_dir / "data" / "outputs" / "novel_audio"
        self.audio_output_dir.mkdir(parents=True, exist_ok=True)

        self.client = OpenAI(base_url="http://127.0.0.1:20128/v1", api_key="sk-d13e798ca7a8589d-jfr5u9-d6a964f4", max_retries=1, timeout=60.0)

    def get_chapters_context(self, start_ch: int, end_ch: int, max_chars: int = 1200) -> str:
        texts = []
        if not self.chapters_dir.exists():
            return ""
        
        for f in sorted(list(self.chapters_dir.glob("**/*.md")) + list(self.chapters_dir.glob("**/*.txt"))):
            m = re.search(r"(?:第|Chương\s*|Chapter\s*|0*)(\d+)", f.name, re.IGNORECASE)
            if m:
                try:
                    ch_num = int(m.group(1))
                    if start_ch <= ch_num <= end_ch:
                        content = f.read_text(encoding="utf-8", errors="ignore")
                        texts.append(f"=== 【Chương {ch_num}】 ===\n{content[:max_chars]}\n")
                except Exception:
                    pass
        return "\n".join(texts)

    def detect_novel_chapter_from_dialogue(self, transcript_text: str, novel_id: str = "Pham nhan tu tien", current_ep_hint: int = 0, user_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Bóc tách lời thoại từ Video/SRT (nguồn tham khảo) và đối chiếu với kho truyện để xác định CHÍNH XÁC chương tương ứng."""
        if not transcript_text or len(transcript_text.strip()) < 10:
            return {"success": False, "error": "Thiếu dữ liệu lời thoại hoặc phụ đề để đối chiếu."}

        chapters = self.repo.list_novel_chapters(novel_id)
        if not chapters:
            return {"success": False, "error": f"Không tìm thấy kho chương truyện của {novel_id}."}

        raw_lines = [l.strip() for l in transcript_text.splitlines() if l.strip() and not re.match(r'^\d+$', l) and '-->' not in l]

        # Lấy các câu thoại tham khảo: nếu ngắn (trailer/clip) thì lấy hết, nếu dài thì lấy đoạn kết 30 câu
        if len(raw_lines) <= 40:
            dialogue_text = "\n".join(raw_lines)
        else:
            dialogue_text = "\n".join(raw_lines[-30:])

        # Trích xuất các số tập / số chương tiềm năng từ user_prompt và current_ep_hint để xác định phạm vi mục lục (catalog)
        extracted_nums = [int(n) for n in re.findall(r'\b\d+\b', user_prompt or '')] if user_prompt else []
        
        # Điểm mốc cơ sở của tập tham khảo:
        base_ep = current_ep_hint if current_ep_hint and current_ep_hint > 0 else (extracted_nums[-1] if extracted_nums else 1)
        base_ch = int(base_ep * 3.873)
        if base_ch <= 0:
            base_ch = 1

        # Xác định phạm vi danh mục chương (Chapter Catalog) bao phủ từ trước tập tham khảo đến sau tập mục tiêu
        max_requested_num = max(extracted_nums) if extracted_nums else base_ep
        if max_requested_num > 500:  # người dùng chỉ định số chương trực tiếp (ví dụ 750)
            max_target_ch = max_requested_num + 15
        elif max_requested_num > 10:  # người dùng chỉ định số tập (ví dụ 194)
            max_target_ch = int(max_requested_num * 3.9) + 20
        else:
            max_target_ch = base_ch + 60

        catalog_start = max(1, base_ch - 15)
        catalog_end = max(base_ch + 60, max_target_ch)

        catalog_items = []
        for ch in chapters:
            c_num = ch.get("chapter_num", 0)
            if catalog_start <= c_num <= catalog_end:
                catalog_items.append(f"- Chương {c_num}: {ch.get('title', '')}")
        catalog_str = "\n".join(catalog_items[:140])

        # Trích xuất đoạn trích (snippets) của các chương xung quanh tập tham khảo để AI đối chiếu lời thoại chính xác
        ref_candidate_objs = [ch for ch in chapters if (base_ch - 12) <= ch.get("chapter_num", 0) <= (base_ch + 15)]
        if not ref_candidate_objs:
            ref_candidate_objs = chapters[:20]

        candidate_snippets = []
        for ch in ref_candidate_objs[:20]:
            ch_num = ch.get("chapter_num", 0)
            t = ch.get("title", "")
            c_res = self.repo.get_chapter_content(novel_id, ch["filename"])
            if c_res.get("success"):
                c_txt = c_res.get("content", "")
                c_clean = re.sub(r'【.*?】|\[.*?\]', '', c_txt)
                snippet = c_clean[:600] + "\n...\n" + c_clean[-600:]
                candidate_snippets.append(f"--- CHƯƠNG {ch_num}: {t} ---\n{snippet}\n")
            else:
                candidate_snippets.append(f"--- CHƯƠNG {ch_num}: {t} ---\n")

        system_prompt = f"""Bạn là BẬC THẦY CỐ VẤN CỐT TRUYỆN HOẠT HÌNH & TIỂU THUYẾT TIÊN HIỆP (am hiểu tường tận Phàm Nhân Tu Tiên, Tiên Nghịch...).

NHIỆM VỤ CỦA BẠN LÀ 'BỘ ÓC AI THÔNG MINH' PHÂN TÍCH TOÀN DIỆN VÀ TỰ ĐỘNG LỰA CHỌN CHƯƠNG NGUYÊN TÁC:
1. ĐỌC VÀ HIỂU SÂU SẮC YÊU CẦU TRONG PROMPT CỦA NGƯỜI DÙNG:
   - Tự động phân tích ngôn ngữ tự nhiên của người dùng (ví dụ: 'Viết tập 194 dựa trên nội dung điểm mốc chương của tập 189', 'viết tiếp tập 190', 'tập sau 192...').
   - Xác định:
     * target_episode: Số tập mục tiêu người dùng muốn viết (ví dụ: 194).
     * reference_episode: Số tập mốc tham khảo xuất phát (ví dụ: 189).
     * QUY TẮC: target_episode là tập đang viết kịch bản. reference_episode là tập tham khảo trước đó.

2. ĐỐI CHIẾU LỜI THOẠI THAM KHẢO VỚI CÁC CHƯƠNG THAM KHẢO (trong danh sách candidate_chapters_snippets):
   - Lời thoại tham khảo dừng chính xác ở chương nào? (detected_end_chapter, detected_chapter_title).
   - Tóm tắt phân cảnh lúc dừng lại (ending_summary).

3. ĐỐI CHIẾU VỚI DANH MỤC CÁC CHƯƠNG NGUYÊN TÁC DƯỚI ĐÂY ĐỂ CHỌN DẢI CHƯƠNG CHO TẬP MỤC TIÊU:
MỤC LỤC CHƯƠNG NGUYÊN TÁC:
{catalog_str}

QUY TẮC PHÂN TÍCH VÀ LỰA CHỌN DẢI CHƯƠNG (target_chapters) - AI TỰ DO PHÂN TÍCH THEO MẠCH PHIM, KHÔNG FIX CỨNG:
   - BỘ ÓC AI tự do đánh giá diễn biến cốt truyện thực tế để quyết định dải chương phù hợp nhất cho tập phim:
     * Tùy theo nhịp độ phân đoạn phim: có thể là 1 chương đàm thoại sâu sắc, 2-3 chương vừa phải, hoặc 4-5 chương nếu tình tiết lướt nhanh, di chuyển vượt ải nhiều hoặc giao tranh dồn dập.
     * NẾU NGƯỜI DÙNG CÓ CHỈ ĐỊNH (ví dụ: 'chương 800 đến 804'): Tôn trọng 100% dải chương người dùng chỉ định.
   - YÊU CẦU BẮT BUỘC VỀ ĐỘ CHUẨN XÁC THEO PHIM:
     * Tình tiết phải chuẩn 100% theo đúng mạch phim và nguyên tác, không được tóm tắt qua loa làm mất các giao tiếp, đối thoại then chốt hoặc biến cố quan trọng.
     * Phải xác định rõ điểm ngắt kết thúc (cliffhanger_point): tập phim có thể dừng dở dang ở nửa chương (ví dụ 50% chương) ngay tại nút thắt kịch tính hoặc dừng cuối chương.
   - NẾU NHẢY CÓC TẬP (ví dụ từ tập 189 nhảy đến tập 194):
     * Tra cứu danh mục chương để chọn dải chương chuẩn xác tương ứng với tập mục tiêu, viết 'bridge_summary' tóm lược các biến cố then chốt giữa 2 mốc tập.
   - NẾU VIẾT TẬP LIỀN KỀ (ví dụ từ 189 viết tiếp 190): target_chapters bắt đầu ngay từ phần tiếp nối của detected_end_chapter (chọn linh hoạt từ 1 đến 5 chương tùy theo nhịp độ tình tiết).

TRẢ VỀ ĐÚNG ĐỊNH DẠNG JSON:
{{
  "target_episode": <số nguyên của tập mục tiêu>,
  "reference_episode": <số nguyên của tập mốc tham khảo>,
  "user_intent_summary": "<tóm tắt yêu cầu của người dùng>",
  "pacing_assessment": "<đánh giá nhịp độ: ví dụ 'Tình tiết nhanh/vượt ải dồn dập, chọn 4-5 chương 809-813' hoặc 'Đấu trí đàm thoại sâu sắc, chọn 1-2 chương'>",
  "detected_end_chapter": <số chương khớp lời thoại tham khảo>,
  "detected_chapter_title": "<tiêu đề chương khớp>",
  "ending_dialogue_match": "<câu thoại khớp trong nguyên tác>",
  "ending_summary": "<tóm tắt đoạn kết tập tham khảo>",
  "start_chapter": <số chương bắt đầu tiếp nối>,
  "start_chapter_percent": <ước lượng % vị trí bắt đầu trong chương đó, từ 0 đến 100, ví dụ 65>,
  "start_cut_point": "<mô tả ngắn gọn điểm bắt đầu, ví dụ: 'Bắt đầu từ ~65% Chương 809 sau phân đoạn Hàn Lập phát giác dấu vết'>",
  "end_chapter": <số chương kết thúc tập phim>,
  "end_chapter_percent": <ước lượng % vị trí kết thúc trong chương đó, từ 0 đến 100, ví dụ 35>,
  "end_cut_point": "<mô tả điểm dừng cliffhanger, ví dụ: 'Dừng ở ~35% Chương 811 lúc Song Vĩ Xà chuẩn bị ra tay ám sát'>",
  "coverage_timeline": "<tóm tắt lộ trình % từng chương, ví dụ: '~65% Chương 809 ➔ 100% Chương 810 ➔ ~35% Chương 811 (Cliffhanger)'>",
  "bridge_summary": "<tóm tắt các sự kiện cầu nối nếu có nhảy tập>",
  "target_chapters": [<danh sách các số nguyên của chương mục tiêu, linh hoạt 1-5 chương theo phân tích AI hoặc prompt>],
  "cliffhanger_point": "<mô tả điểm dừng kịch tính làm cliffhanger ở giữa chương hay cuối chương>",
  "reasoning": "<giải thích lý do lựa chọn dải chương này cho tập mục tiêu>"
}}"""
        payload = {
            "task": "analyze_prompt_intent_and_match_chapters",
            "user_prompt": user_prompt or "",
            "reference_dialogue": dialogue_text,
            "candidate_chapters_snippets": candidate_snippets[:20]
        }

        try:
            from capcut_api.api.gui_app import build_ai_translation_config, call_ai_json_object
            ai_config = build_ai_translation_config({}, purpose="context")
            res = call_ai_json_object(ai_config, system_prompt, payload, line_count=40)
            if isinstance(res, dict) and res.get("detected_end_chapter"):
                res["success"] = True
                end_ch = res.get("detected_end_chapter")
                ch_obj = next((ch for ch in chapters if ch.get("chapter_num") == end_ch), None)
                if ch_obj and ch_obj.get("title"):
                    raw_title = ch_obj["title"]
                    # Ưu tiên lấy phần tiếng Việt trong ngoặc đơn nếu có
                    vi_match = re.search(r'\(([^)]+)\)', raw_title)
                    if vi_match:
                        res["detected_chapter_title"] = vi_match.group(1).strip()
                    else:
                        clean_t = re.sub(r'[\u4e00-\u9fff]+', '', raw_title).strip(' :-_#')
                        res["detected_chapter_title"] = clean_t or f"Chương {end_ch}"

                # Làm sạch toàn bộ chữ Hán còn sót lại và dấu ?? trong các trường tóm tắt
                clean_fields = [
                    "bridge_summary", "ending_summary", "user_intent_summary", "pacing_assessment", 
                    "cliffhanger_point", "reasoning", "start_cut_point", "end_cut_point", "coverage_timeline"
                ]
                for key in clean_fields:
                    if res.get(key) and isinstance(res[key], str):
                        clean_val = re.sub(r'[\u4e00-\u9fff]+', '', res[key])
                        clean_val = re.sub(r'\?{2,}', '', clean_val)
                        clean_val = re.sub(r'\(\s*\)', '', clean_val)
                        clean_val = re.sub(r'\s{2,}', ' ', clean_val).strip()
                        res[key] = clean_val

                # Tính toán % chính xác của điểm dừng nếu tìm thấy câu thoại trong nguyên tác
                if ch_obj:
                    c_res = self.repo.get_chapter_content(novel_id, ch_obj["filename"])
                    if c_res.get("success"):
                        c_text = c_res.get("content", "")
                        dial_match = res.get("ending_dialogue_match")
                        if dial_match and len(dial_match.strip()) > 5:
                            clean_dial = re.sub(r'[^\w\s]', '', dial_match.strip())
                            clean_ctxt = re.sub(r'[^\w\s]', '', c_text)
                            pos = clean_ctxt.find(clean_dial[:25])
                            if pos >= 0 and len(clean_ctxt) > 0:
                                res["start_chapter_percent"] = max(5, min(95, round((pos / len(clean_ctxt)) * 100)))

                # Đồng bộ danh sách chương do AI phân tích linh hoạt (không ép cứng số lượng)
                if res.get("target_chapters"):
                    try:
                        res["target_chapters"] = [int(c) for c in res["target_chapters"]]
                    except Exception:
                        pass
                if res.get("next_episode_chapters"):
                    try:
                        res["next_episode_chapters"] = [int(c) for c in res["next_episode_chapters"]]
                    except Exception:
                        pass
                if res.get("target_chapters") and not res.get("next_episode_chapters"):
                    res["next_episode_chapters"] = res["target_chapters"]

                # Đảm bảo có đầy đủ coverage_timeline, start_cut_point và end_cut_point
                target_chs = res.get("target_chapters") or []
                start_pct = res.get("start_chapter_percent") or 60
                end_pct = res.get("end_chapter_percent") or 35

                if target_chs:
                    if len(target_chs) == 1:
                        timeline = f"Chương {target_chs[0]} (từ ~{start_pct}% đến ~{end_pct}%)"
                    elif len(target_chs) == 2:
                        timeline = f"Chương {target_chs[0]} (từ ~{start_pct}%) ➔ Chương {target_chs[1]} (đến ~{end_pct}% - Cliffhanger)"
                    else:
                        parts = [f"Chương {target_chs[0]} (từ ~{start_pct}%)"]
                        for mid_c in target_chs[1:-1]:
                            parts.append(f"Chương {mid_c} (100%)")
                        parts.append(f"Chương {target_chs[-1]} (đến ~{end_pct}% - Cliffhanger)")
                        timeline = " ➔ ".join(parts)
                    
                    if not res.get("coverage_timeline"):
                        res["coverage_timeline"] = timeline
                    if not res.get("start_cut_point"):
                        res["start_cut_point"] = f"Bắt đầu tiếp nối từ ~{start_pct}% Chương {target_chs[0]}"
                    if not res.get("end_cut_point"):
                        res["end_cut_point"] = f"Dừng ở ~{end_pct}% Chương {target_chs[-1]} (Điểm ngắt kịch tính Cliffhanger)"
                return res
        except Exception as e:
            logger.error(f"Lỗi AI matching chapter: {e}")

        return {"success": False, "error": "Không thể dò tìm chương từ lời thoại tham khảo."}

    def get_dynamic_novel_context(self, novel_id: str, transcript_text: str = "", prompt: Optional[str] = None, current_episode_num: int = 1, next_episode_num: int = 0, max_chars: int = 4000) -> Tuple[str, Dict[str, Any]]:
        """Sử dụng BỘ ÓC AI để phân tích toàn diện Prompt người dùng, lời thoại video và tự động trích xuất dải chương tương ứng."""
        chapters = self.repo.list_novel_chapters(novel_id)
        if not chapters:
            return "", {"error": f"Không tìm thấy kho chương truyện {novel_id}"}

        # 1. Nếu người dùng chỉ định rõ ràng số chương trong prompt (ví dụ: "chương 809 đến 810", hoặc "chương 809")
        if prompt:
            m_range = re.search(r'(?:chương|chuong|chapter|ch)\s*(\d+)\s*(?:đến|tới|-|->)\s*(?:chương|chuong|chapter|ch)?\s*(\d+)', prompt, re.IGNORECASE)
            m_single = re.search(r'(?:chương|chuong|chapter|ch)\s*(\d+)', prompt, re.IGNORECASE)
            if m_range:
                start_ch = int(m_range.group(1))
                end_ch = int(m_range.group(2))
                target_chapter_nums = [c for c in range(start_ch, end_ch + 1)]
            elif m_single:
                target_num = int(m_single.group(1))
                # Nhịp phim 3D chuẩn: 1 tập chuyển thể 1 đến 2 chương (chương chỉ định + chương kế tiếp)
                target_chapter_nums = [target_num, target_num + 1]
            else:
                target_chapter_nums = []

            # Giới hạn an toàn tối đa 6 chương nếu người dùng nhập dải quá rộng (tránh tràn bộ nhớ context), còn lại tôn trọng 100% chỉ định
            if len(target_chapter_nums) > 6:
                target_chapter_nums = target_chapter_nums[:6]

            if target_chapter_nums:
                texts = []
                for ch_num in target_chapter_nums:
                    ch_obj = next((ch for ch in chapters if ch.get("chapter_num") == ch_num), None)
                    if ch_obj:
                        res = self.repo.get_chapter_content(novel_id, ch_obj["filename"])
                        if res.get("success"):
                            clean_c = re.sub(r'【.*?】|\[.*?\]', '', res.get('content', ''))
                            texts.append(f"=== 【{ch_obj['title']}】 ===\n{clean_c[:12000]}\n")
                if texts:
                    start_pct = 70
                    end_pct = 35
                    if len(target_chapter_nums) == 1:
                        timeline = f"Chương {target_chapter_nums[0]} (từ ~{start_pct}% đến ~{end_pct}%)"
                    elif len(target_chapter_nums) == 2:
                        timeline = f"Chương {target_chapter_nums[0]} (từ ~{start_pct}%) ➔ Chương {target_chapter_nums[1]} (đến ~{end_pct}% - Cliffhanger)"
                    else:
                        parts = [f"Chương {target_chapter_nums[0]} (từ ~{start_pct}%)"]
                        for mid_c in target_chapter_nums[1:-1]:
                            parts.append(f"Chương {mid_c} (100%)")
                        parts.append(f"Chương {target_chapter_nums[-1]} (đến ~{end_pct}% - Cliffhanger)")
                        timeline = " ➔ ".join(parts)

                    return "\n".join(texts), {
                        "success": True,
                        "detected_end_chapter": target_chapter_nums[0],
                        "target_chapters": target_chapter_nums,
                        "next_episode_chapters": target_chapter_nums,
                        "start_chapter_percent": start_pct,
                        "end_chapter_percent": end_pct,
                        "start_cut_point": f"Tiếp nối từ ~{start_pct}% Chương {target_chapter_nums[0]}",
                        "end_cut_point": f"Dừng ở ~{end_pct}% Chương {target_chapter_nums[-1]} (Điểm ngắt kịch tính Cliffhanger)",
                        "coverage_timeline": timeline,
                        "pacing_assessment": f"Chỉ định dải {len(target_chapter_nums)} chương theo prompt",
                        "reasoning": f"Chỉ định theo prompt: Chương {', '.join(str(c) for c in target_chapter_nums)}"
                    }

        # 2. Để BỘ ÓC AI tự động đọc hiểu Prompt và phân tích dải chương phù hợp
        detection = self.detect_novel_chapter_from_dialogue(transcript_text, novel_id=novel_id, current_ep_hint=current_episode_num, user_prompt=prompt)
        if detection.get("success"):
            target_chapters = detection.get("target_chapters") or detection.get("next_episode_chapters") or []
            detected_end_ch = detection.get("detected_end_chapter")

            target_chapter_nums = []
            for c in target_chapters:
                try:
                    target_chapter_nums.append(int(c))
                except (ValueError, TypeError):
                    pass

            # Giới hạn an toàn tối đa 6 chương để tránh quá tải token, cho phép AI linh hoạt chọn từ 1 đến 5 chương theo nhịp phim
            if len(target_chapter_nums) > 6:
                target_chapter_nums = target_chapter_nums[:6]

            # Nếu viết tập liền kề và tập trước dừng ở giữa chương, đảm bảo chương kết thúc đứng đầu làm cầu nối
            target_ep = detection.get("target_episode", next_episode_num)
            ref_ep = detection.get("reference_episode", current_episode_num)
            if target_ep and ref_ep and target_ep == ref_ep + 1 and detected_end_ch:
                if detected_end_ch not in target_chapter_nums:
                    target_chapter_nums = [detected_end_ch] + [c for c in target_chapter_nums if c != detected_end_ch]

            if not target_chapter_nums and detected_end_ch:
                target_chapter_nums = [detected_end_ch, detected_end_ch + 1]

            detection["target_chapters"] = target_chapter_nums
            detection["next_episode_chapters"] = target_chapter_nums

            # Đồng bộ lại coverage_timeline nếu target_chapter_nums thay đổi
            start_pct = detection.get("start_chapter_percent") or 60
            end_pct = detection.get("end_chapter_percent") or 35
            if target_chapter_nums:
                if len(target_chapter_nums) == 1:
                    timeline = f"Chương {target_chapter_nums[0]} (từ ~{start_pct}% đến ~{end_pct}%)"
                elif len(target_chapter_nums) == 2:
                    timeline = f"Chương {target_chapter_nums[0]} (từ ~{start_pct}%) ➔ Chương {target_chapter_nums[1]} (đến ~{end_pct}% - Cliffhanger)"
                else:
                    parts = [f"Chương {target_chapter_nums[0]} (từ ~{start_pct}%)"]
                    for mid_c in target_chapter_nums[1:-1]:
                        parts.append(f"Chương {mid_c} (100%)")
                    parts.append(f"Chương {target_chapter_nums[-1]} (đến ~{end_pct}% - Cliffhanger)")
                    timeline = " ➔ ".join(parts)
                detection["coverage_timeline"] = timeline
                if not detection.get("start_cut_point"):
                    detection["start_cut_point"] = f"Bắt đầu tiếp nối từ ~{start_pct}% Chương {target_chapter_nums[0]}"
                if not detection.get("end_cut_point"):
                    detection["end_cut_point"] = f"Dừng ở ~{end_pct}% Chương {target_chapter_nums[-1]} (Điểm ngắt kịch tính Cliffhanger)"

            texts = []
            for ch_num in target_chapter_nums:
                ch_obj = next((ch for ch in chapters if ch.get("chapter_num") == ch_num), None)
                if ch_obj:
                    res = self.repo.get_chapter_content(novel_id, ch_obj["filename"])
                    if res.get("success"):
                        clean_c = re.sub(r'【.*?】|\[.*?\]', '', res.get('content', ''))
                        texts.append(f"=== 【{ch_obj['title']}】 ===\n{clean_c[:12000]}\n")
            if texts:
                return "\n".join(texts), detection

        return "", {"error": "Cần có video hoặc file SRT tham khảo tại Step 1-2 để AI đọc lời thoại đối chiếu!"}

        # 3. Nếu không có transcript, báo lỗi rõ ràng
        return "", {"error": "Cần có video hoặc file SRT tham khảo tại Step 1-2 để AI đọc lời thoại đối chiếu!"}

    def _build_storytelling_from_context(self, novel_title: str, next_ep: int, current_summary: str, next_novel_context: str) -> Dict[str, Any]:
        """Biên kịch Thuyết minh & Kể chuyện Review Anime/Truyện đỉnh cao chuẩn phong cách YouTube (đối thoại sống động, giao nhân vật, phân tích thế cục)."""
        import concurrent.futures
        import urllib.parse

        def translate_single(t: str) -> str:
            if not t or not re.search(r'[\u4e00-\u9fff]', t):
                return t
            endpoints = [
                "https://translate.googleapis.com/translate_a/single?client=gtx&sl=zh-CN&tl=vi&dt=t&q=",
                "https://translate.googleapis.com/translate_a/single?client=dict-chrome-ex&sl=zh-CN&tl=vi&dt=t&q="
            ]
            for ep in endpoints:
                try:
                    url = ep + urllib.parse.quote(t)
                    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                    r = requests.get(url, headers=headers, timeout=6)
                    if r.status_code == 200:
                        res = r.json()
                        trans = "".join(s[0] for s in res[0] if s and s[0]).strip()
                        if trans:
                            return trans
                except Exception:
                    time.sleep(0.1)
            return t

        # Tách các đoạn văn nguyên tác có độ dài phù hợp
        raw_paragraphs = [p.strip() for p in next_novel_context.split("\n") if len(p.strip()) > 20 and not p.strip().startswith("===")]
        if not raw_paragraphs:
            raw_paragraphs = [
                f"{novel_title} tiếp tục diễn biến kịch tính với những trận đối đầu cam go giữa các thế lực.",
                f"Hàn Lập tiến vào mật thất chuẩn bị tu luyện tầng tiếp theo, linh khí xung quanh dao động dữ dội.",
                f"Những thế lực xung quanh bắt đầu rục rịch điều động nhân mã, một trận chiến lớn sắp sửa bùng nổ."
            ]

        # Lấy tối đa 35 đoạn để đảm bảo video dài dặn 8-15 phút
        selected_raw = raw_paragraphs[:35]

        # Dịch song song siêu tốc qua ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            translated_paragraphs = list(executor.map(translate_single, selected_raw))

        # TỰ ĐỘNG CHUYỂN HÓA VĂN HỌC THÀNH VĂN PHONG REVIEW THUYẾT MINH CHUYÊN NGHIỆP
        scenes = []

        # Scene 1: Mở đầu Hook & Recap thông minh
        if current_summary and len(current_summary.strip()) > 15 and "mặc định" not in current_summary.lower():
            opening_text = f"{novel_title} tập {next_ep}. Ở cuối tập trước, {current_summary.strip()[:150]}. Trong tập này chúng ta cùng theo dõi những diễn biến tiếp theo nha."
        else:
            opening_text = f"{novel_title} tập {next_ep}. Chào mừng các bạn đã quay trở lại với hành trình tu tiên đầy hấp dẫn. Trong tập này chúng ta cùng xem tiếp những diễn biến tiếp theo nha."

        scenes.append({
            "scene_id": 1,
            "voiceover": opening_text,
            "visual_prompt": f"Cinematic anime {novel_title}, dramatic intro scene, 4k quality",
            "animation": "Zoom In"
        })

        # Danh sách liên từ & lời dẫn chuyển cảnh mượt mà
        transitions = [
            "Trở lại bối cảnh lúc này,",
            "Không ngoài dự đoán,",
            "Thấy đối phương xuất hiện,",
            "Ánh mắt Hàn Lập chớp động vài cái, sau khi cười thầm một tiếng bèn",
            "Lúc này tại hiện trường,",
            "Sau một hồi quan sát kỹ lưỡng,",
            "Trước tình thế cấp bách,",
            "Hàn Lập sờ sờ cằm âm thầm tự đánh giá, sau đó",
            "Đối phương nghe vậy sắc mặt có chút biến đổi, lập tức",
            "Cùng lúc đó, bốn phía xung quanh bắt đầu xuất hiện dao động dữ dội,"
        ]

        animations = ["Zoom In", "Zoom Out", "Pan Left", "Pan Right"]

        # TỪ ĐIỂN THUẬT NGỮ KIẾM HIỆP TU TIÊN & CHUẨN HÓA DANH TỪ RIÊNG & ĐỐI THOẠI
        tu_tien_dict = [
            (r'\bngười [Aa]nh k[ỳy]\b', 'Nguyên Anh Kỳ'),
            (r'\bngười [Aa]nh\b', 'Nguyên Anh'),
            (r'\bkết đang k[ỳy]\b', 'Kết Đan Kỳ'),
            (r'\bkết đang\b', 'Kết Đan'),
            (r'\bthử thách đẫm máu\b', 'Huyết Sắc Thí Luyện'),
            (r'\bvùng cấm\b', 'Cấm Địa'),
            (r'\bchuyên gia\b', 'cao thủ'),
            (r'\bcâu cá ở vùng nước có sóng gió\b', 'đục nước béo cò'),
            (r'\bcụ quốc minh\b', 'Cửu Quốc Minh'),
            (r'\bthiên đạo minh\b', 'Thiên Đạo Minh'),
            (r'\blạc vân tông\b', 'Lạc Vân Tông'),
            (r'\blạc vân phái\b', 'Lạc Vân Tông'),
            (r'\bhoàng phong cốc\b', 'Hoàng Phong Cốc'),
            (r'\b[Hh]an [Ll]i\b', 'Hàn Lập'),
            (r'\b[Hh]àng [Ll]ập\b', 'Hàn Lập'),
            (r'\b[Hh]àn anh\b', 'Hàn huynh'),
            (r'\b[Hh]an anh\b', 'Hàn huynh'),
            (r'\b[Hh]àng sư đệ\b', 'Hàn sư đệ'),
            (r'\b[Hh]àng mỗ\b', 'Hàn mỗ'),
            (r'\b[Hh]an [Zz]hu\b', 'Hàn Chú'),
            (r'\b[Ee]rluzi\b', 'Nhị Lăng Tử'),
            (r'\b[Mm]ei [Nn]ing\b', 'Mai Ngưng'),
            (r'\b[Mm]ei tiểu thư\b', 'Mai tiểu thư'),
            (r'\b[Tt]ử [Ll]inh\b', 'Tử Linh'),
            (r'\bnam lũng hầu\b', 'Nam Lũng Hầu'),
            (r'\b[Tt]rụy [Mm]a [Cc]ốc\b', 'Trụy Ma Cốc'),
            (r'\b[Cc]huyện [Mm]a [Cc]ốc\b', 'Trụy Ma Cốc'),
            (r'\b[Mm]u [Pp]eiling\b', 'Mộ Bái Linh'),
            (r'\bmộ phải linh\b', 'Mộ Bái Linh'),
            (r'\bmộ bái linh\b', 'Mộ Bái Linh'),
            (r'\bhỏa long đồng tử\b', 'Hỏa Long Đồng Tử'),
            (r'\bpháp sĩ xa lạ\b', 'Pháp Sĩ Mộ Lan'),
            (r'\blữ lạc\b', 'Lữ Lạc'),
            (r'\blữ lão\b', 'Lữ trưởng lão'),
            (r'\blữ tiền bối\b', 'Lữ tiền bối'),
            (r'\blam tiền bối\b', 'Lam tiền bối'),
            (r'\blão già họ mã\b', 'lão già họ Mã'),
            (r'\bbạc đà tử\b', 'Bạc đà tử'),
            (r'\btrưởng lão tóc bạc trình\b', 'Trình trưởng lão tóc bạc'),
            (r'\bthiên phong huyền ba trận\b', 'Thiên Phong Huyền Ba Trận'),
            (r'\bhoàng long sơn\b', 'Hoàng Long Sơn'),
            (r'\bquỳnh bàn lầu cát\b', 'Quỳnh Bàn Lâu Các'),
            (r'\btrọc mi đại hán\b', 'Trọc Mi đại hán'),
            (r'\blục sắc quái vụ\b', 'quái vụ màu xanh lục'),
            (r'\bbích lục vụ hải\b', 'biển sương mù xanh biếc'),
            (r'\bngười đẹp xiu\b', 'nữ tu'),
            (r'\bđẹp xiu\b', 'nữ tu xinh đẹp'),
            (r'\bvợ lẽ\b', 'thị thiếp'),
            (r'\btây quốc\b', 'Khê Quốc'),
            (r'\bthuốc tiên không thể được hình thành\b', 'không thể Kết Đan thành công'),
            (r'\bhòa thượng cao cấp\b', 'tu sĩ cao cấp'),
            (r'\bhòa thượng\b', 'tu sĩ'),
            (r'\bHan khác với\b', 'Hàn mỗ khác với'),
            (r'\bchạm vào đàn ông\. Là chuyện tình cảm giữa phụ nữ\b', 'vướng bận chuyện nam nữ tình trường'),
            (r'\bcon đường trường sinh bất lão\b', 'đại đạo trường sinh'),
            (r'\bem gái tôi\b', 'muội muội của ta'),
            (r'\bem gái\b', 'muội muội')
        ]

        def polish_tu_tien_text(text: str) -> str:
            t = text
            for pat, repl in tu_tien_dict:
                t = re.sub(pat, repl, t, flags=re.IGNORECASE)
            return t

        for idx, vi_text in enumerate(translated_paragraphs):
            clean_p = re.sub(r'【.*?】|\[.*?\]', '', vi_text).strip()
            if len(clean_p) < 15:
                continue

            # Chuẩn hóa lời thoại có ngoặc kép và danh xưng
            clean_p = clean_p.replace('“', '"').replace('”', '"').replace("‘", "'").replace("’", "'")
            clean_p = polish_tu_tien_text(clean_p)

            # Gọt dũa lời dẫn chuyện review
            lead = transitions[idx % len(transitions)] if idx > 0 and not clean_p.startswith('"') and idx % 3 == 1 else ""
            if lead and not clean_p.lower().startswith(("khi", "lúc", "sau", "tuy", "nhưng", "đột nhiên", "trở lại")):
                enhanced_vo = f"{lead} {clean_p[0].lower() + clean_p[1:]}"
            else:
                enhanced_vo = clean_p

            scenes.append({
                "scene_id": len(scenes) + 1,
                "voiceover": enhanced_vo,
                "visual_prompt": f"Anime fantasy cultivation battle, character dialogue, cinematic lighting, scene {idx+1}",
                "animation": animations[idx % len(animations)]
            })

        # Scene cuối: Outro kêu gọi tương tác
        scenes.append({
            "scene_id": len(scenes) + 1,
            "voiceover": f"Tới đây cũng tạm thời kết thúc nội dung của tập hôm nay rồi. Cảm ơn các bạn đã xem hết video. Nếu muốn mình ra thêm tập {next_ep + 1} thì đừng quên để lại ý kiến dưới phần bình luận nhé. Còn bây giờ xin chào và hẹn gặp lại.",
            "visual_prompt": f"Anime outro screen with subscribe and like button, fantasy background",
            "animation": "Zoom Out"
        })

        return {
            "title": f"{novel_title} Tập {next_ep}",
            "opening_hook": scenes[0]["voiceover"],
            "scenes": scenes,
            "closing_outro": scenes[-1]["voiceover"]
        }

    def _find_reference_review_script(self, novel_id: str, next_ep: int) -> Optional[List[str]]:
        """Tìm kiếm kịch bản review mẫu chất lượng cao trong thư mục data hoặc Downloads của User."""
        candidates = [
            Path(f"data/novels/{novel_id}/tap_{next_ep}_master_review.txt"),
            Path(f"data/novels/{novel_id}/tap_{next_ep}_sample_review.txt"),
            Path(f"data/novels/{novel_id}/tap_{next_ep}.txt")
        ]
        
        # Tìm trong thư mục Downloads của User
        try:
            user_dl = Path(os.environ.get("USERPROFILE", r"C:\Users\admin.TRANANH")) / "Downloads"
            if user_dl.exists():
                for p in user_dl.glob(f"*{next_ep}*.srt"):
                    candidates.append(p)
                for p in user_dl.glob(f"*{next_ep}*.txt"):
                    candidates.append(p)
        except Exception:
            pass
                
        # Bộ từ điển sửa lỗi ASR/OCR cho bản ghi thuyết minh tải về
        typo_fixes = [
            (r'\bPhạm Dân\b', 'Phàm Nhân'),
            (r'\blĩnh hồ\b', 'Lệnh Hồ'),
            (r'\btruyện Ma Cốc\b', 'Trụy Ma Cốc'),
            (r'\bchuyện ma Cốc\b', 'Trụy Ma Cốc'),
            (r'\bchuyện Ma Cốc\b', 'Trụy Ma Cốc'),
            (r'\bđang lũng hầu\b', 'Nam Lũng Hầu'),
            (r'\bvị lữ sư huynh\b', 'vị Lữ sư huynh'),
            (r'\bMộ Phải Linh\b', 'Mộ Bái Linh'),
            (r'\bân gần\b', 'ân cần'),
            (r'\bvua thuận\b', 'ngoan ngoãn'),
            (r'\bchuyện tình nam của Uyển\b', 'chuyện tình cảm của Nam Cung Uyển'),
            (r'\bHàng sư đệ\b', 'Hàn sư đệ'),
            (r'\bHàng Lập\b', 'Hàn Lập'),
            (r'\bHạc Lập\b', 'Hàn Lập'),
            (r'\bhàng làm\b', 'Hàn Lập'),
            (r'\bhàng bộ\b', 'Hàn mỗ'),
            (r'\bHàng bộ\b', 'Hàn mỗ'),
            (r'\bchêu chọc\b', 'trêu chọc'),
            (r'\bchêu đợ\b', 'trêu đùa'),
            (r'\bMộ Lan Dân\b', 'Pháp Sĩ Mộ Lan'),
            (r'\bngười Mộ Lang\b', 'người Mộ Lan'),
            (r'\bPháp sĩ Mộ Lang\b', 'Pháp Sĩ Mộ Lan'),
            (r'\bngười Mộ Lan\b', 'người Mộ Lan'),
            (r'\bngười Anh\b', 'Nguyên Anh'),
            (r'\bngười anh\b', 'Nguyên Anh'),
            (r'\bcụ quốc minh\b', 'Cửu Quốc Minh'),
            (r'\bcửa quốc Minh\b', 'Cửu Quốc Minh'),
            (r'\bCố Minh\b', 'Cửu Quốc Minh'),
            (r'\bchính ba lưỡng đạo\b', 'Chính Ma lưỡng đạo'),
            (r'\bchữ lão chính ma\b', 'trưởng lão Chính Ma'),
            (r'\blão quá tán tu\b', 'lão quái tán tu'),
            (r'\bbố diệp tông\b', 'Bố Diệp Tông'),
            (r'\bhóa ý môn\b', 'Hóa Ý Môn'),
            (r'\bthích phu dân\b', 'Thích Phu Nhân'),
            (r'\btừ đại thể lực\b', 'tứ đại thế lực'),
            (r'\bchi đều dân chủ\b', 'chia đều nhân số'),
            (r'\bdo sĩ An tạo thành\b', 'do tu sĩ tạo thành'),
            (r'\bĐiền Thiên Thành\b', 'Bình Thiên Thành'),
            (r'\bgâ lệnh\b', 'nghe lệnh'),
            (r'\bchỉ hoảng thế công\b', 'trì hoãn thế công'),
            (r'\blàm mổ\b', 'lão mỗ'),
            (r'\bsơ nỗi\b', 'sôi nổi'),
            (r'\bdu sơ ngoạn thủy\b', 'du sơn ngoạn thủy'),
            (r'\bgửi liên tông cốc sông bồ\b', 'người của Liên Tông Cốc'),
            (r'\bTrọc Mi đại hán\b', 'Trọc Mi đại hán'),
            (r'\bthiên phong huyền ba trận\b', 'Thiên Phong Huyền Ba Trận'),
            (r'\bbạc đà tử\b', 'Bạc đà tử'),
            (r'\bbạc tiền bối\b', 'Bạc tiền bối')
        ]

        for cand in candidates:
            if cand.exists():
                try:
                    content = cand.read_text(encoding="utf-8", errors="ignore")
                    for pat, repl in typo_fixes:
                        content = re.sub(pat, repl, content, flags=re.IGNORECASE)

                    if cand.suffix.lower() == ".srt":
                        blocks = [b.strip() for b in content.split("\n\n") if b.strip()]
                        raw_sentences = []
                        for b in blocks:
                            lines = b.splitlines()
                            if len(lines) >= 3:
                                t = " ".join(lines[2:]).strip()
                                if t:
                                    raw_sentences.append(t)
                        full_merged = " ".join(raw_sentences)
                        # Tách theo câu hoàn chỉnh
                        pattern = r'(?<=[.!?…])\s+(?=[A-ZÀ-Ỹ0-9"“])'
                        chunks = re.split(pattern, full_merged)
                        clean_res = [re.sub(r'\s+', ' ', c).strip() for c in chunks if c.strip()]
                        if len(clean_res) >= 5:
                            return clean_res
                    else:
                        lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("[")]
                        if len(lines) >= 5:
                            return lines
                except Exception:
                    continue
        return None

    def generate_script(self, current_summary: str, next_novel_context: str, current_ep: int, next_ep: int, novel_title: str = "Phàm Nhân Tu Tiên", custom_prompt: Optional[str] = None, detection_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Tạo Kịch Bản Thuyết Minh AI chuẩn phong cách Review hoạt hình Tiên Hiệp triệu view, độ dài khoảng 15 phút (2,200 - 3,000 từ)."""
        
        # 1. Phân tích prompt của người dùng để xác định phong cách & trọng tâm
        prompt_lower = (custom_prompt or "").lower()
        style_instruction = "Phong cách thuyết minh kể chuyện review hoạt hình 3D dí dỏm, cuốn hút, bình luận hóm hỉnh ('Hàn lão ma', 'lão ma nhà ta'), miêu tả các chiêu thức và diễn biến kịch tính, hấp dẫn."
        if any(w in prompt_lower for w in ["hài", "dí dỏm", "vui", "cuốn hút"]):
            style_instruction = "Phong cách dí dỏm, châm biếm sâu cay hành vi của kẻ phản bội, khen ngợi độ 'cẩn thận như quỷ' của Hàn Lập, tạo tiếng cười và tương tác sảng khoái cho người xem."
        elif any(w in prompt_lower for w in ["đại chiến", "chiến đấu", "hoành tráng", "gay cấn"]):
            style_instruction = "Phong cách đại chiến hoành tráng, dồn dập, miêu tả chi tiết uy lực từng thần thông pháp bảo (Tử La Cực Hỏa, Tịch Tà Thần Lôi, Phụ Linh Thuật, Song Vĩ Phỉ Thúy Xà), nhịp điệu dồn dập nghẹt thở."
        elif any(w in prompt_lower for w in ["spoiler", "trailer"]):
            style_instruction = "Phong cách phân tích spoiler trailer bóc tách các tình tiết then chốt, giải mã bí ẩn diễn biến sắp tới."

        # Nhận diện yêu cầu thời lượng / độ dài từ Prompt (hoặc để BỘ ÓC AI tự do quyết định)
        m_dur = re.search(r'(\d+)\s*(?:phút|p|min)', prompt_lower)
        if m_dur:
            user_mins = int(m_dur.group(1))
            user_words = user_mins * 160
            duration_instruction = f"Mục tiêu thời lượng: Khoảng {user_mins} PHÚT theo đúng yêu cầu trong prompt (Tương đương ~{user_words} từ tiếng Việt)."
        elif any(w in prompt_lower for w in ["ngắn", "tóm tắt nhanh", "cô đọng"]):
            duration_instruction = "Mục tiêu thời lượng: Ngắn gọn, súc tích (Khoảng 8 - 10 PHÚT, tương đương 1,200 - 1,600 từ tiếng Việt)."
        elif any(w in prompt_lower for w in ["chi tiết", "dài", "kỹ"]):
            duration_instruction = "Mục tiêu thời lượng: Đào sâu chi tiết, đầy đủ thoại và biến cố (Khoảng 18 - 25 PHÚT, tương đương 2,800 - 3,800 từ tiếng Việt)."
        else:
            duration_instruction = "Mục tiêu thời lượng: Do BỘ ÓC AI TỰ DO QUYẾT ĐỊNH ĐỘ DÀI PHÙ HỢP NHẤT (số phân cảnh, số từ) dựa trên dung lượng tình tiết thực tế của các chương nguyên tác và nhịp độ phim (thường dao động tự nhiên từ 12 - 20 PHÚT, tương đương 1,800 - 3,000 từ, TUYỆT ĐỐI KHÔNG FIX CỨNG)."

        # Xử lý trường hợp nhảy cóc tập (ví dụ 189 -> 194) hay nối tiếp liền kề (189 -> 190)
        target_ep_val = next_ep
        ref_ep_val = current_ep
        bridge_info = (detection_info or {}).get("bridge_summary", "")
        start_cut = (detection_info or {}).get("start_cut_point") or ""
        end_cut = (detection_info or {}).get("end_cut_point") or ""
        timeline = (detection_info or {}).get("coverage_timeline") or ""
        is_jump = target_ep_val > (ref_ep_val + 1)

        if is_jump and bridge_info:
            continuity_block = f"""1. TÌNH HUỐNG NHẢY CÓC TẬP (TỪ TẬP {ref_ep_val} NHẢY ĐẾN TẬP {target_ep_val}):
   - Bạn được cung cấp đoạn cầu nối tóm tắt các tập trung gian đã qua:
     "{bridge_info}"
   - PHẠM VI TRÍCH XUẤT (% TỪNG CHƯƠNG): {timeline}
   - ĐIỂM BẮT ĐẦU: {start_cut}
   - ĐIỂM NGẮT CLIFFHANGER: {end_cut}
   - MỞ ĐẦU (OPENING HOOK): Chào mừng khán giả đến với video review TẬP {target_ep_val} hôm nay (ĐÂY LÀ TẬP ĐANG REVIEW). Tận dụng đoạn cầu nối trên để tóm lược ngắn gọn 2-3 câu các biến cố trung gian then chốt đã qua, rồi bùng nổ dẫn nhập vào biến cố chính của TẬP {target_ep_val}!
   - NỘI DUNG CỐT TRUYỆN: Tập trung 100% vào các sự kiện và nhân vật thực tế trong văn bản tiểu thuyết 'next_novel_context' của TẬP {target_ep_val} (TUYỆT ĐỐI KHÔNG quay lại miêu tả chi tiết trận chiến hay đối thoại của Tập {ref_ep_val} cũ). Hồi 1 bắt đầu ngay từ những diễn biến đầu tiên của dải chương thuộc Tập {target_ep_val}!"""
        else:
            continuity_block = f"""1. XÁC ĐỊNH ĐIỂM DỪNG & CẦU NỐI CHUYỂN TIẾP (BÁM SÁT 100% SỰ THẬT TẬP TRƯỚC):
   - Đọc kỹ phần 'reference_dialogue_summary' (nơi tập trước Tập {ref_ep_val} vừa dừng lại) và phần mở đầu của Chương đầu tiên trong 'next_novel_context'.
   - PHẠM VI TRÍCH XUẤT (% TỪNG CHƯƠNG): {timeline}
   - ĐIỂM BẮT ĐẦU: {start_cut}
   - ĐIỂM NGẮT CLIFFHANGER: {end_cut}
   - TUYỆT ĐỐI KHÔNG DÙNG VĂN MẪU SÁO RỖNG HOẶC TỰ BỊA ĐẶT (như: 'sau khi tiếng chém giết rền trời của cuộc chiến tạm thời lắng xuống', 'chiến trường đẫm máu'...). Nếu tập trước là đàm đạo, tu luyện, mật đàm, họp bàn tông môn hay di chuyển, HÃY MIÊU TẢ CHÍNH XÁC không khí đàm luận, sự tính toán mưu lược hoặc bước chuyển dịch của nhân vật!
   - BẮT BUỘC bắt đầu viết tiếp liền mạch từ chính điểm dừng đó vào đầu Chương đầu tiên của 'next_novel_context', tuyệt đối không được bịa đặt chiến trận không có thật."""

        system_prompt = f"""Bạn là BẬC THẦY BIÊN KỊCH & KỂ CHUYỆN REVIEW ANIME / HOẠT HÌNH TIÊN HIỆP 3D TRIỆU VIEW (như kênh Review Phim Tu Tiên, Ghiền Hoạt Hình 3D).

BẠN ĐÓNG VAI TRÒ LÀ 'BỘ ÓC AI THÔNG MINH' TỰ ĐỘNG PHÂN TÍCH VÀ BIÊN SOẠN KỊCH BẢN CHO TẬP KẾ TIẾP DỰA TRÊN NGUỒN THAM KHẢO VÀ NGUYÊN TÁC TIỂU THUYẾT.

NHIỆM VỤ:
Biên soạn toàn bộ KỊCH BẢN THUYẾT MINH REVIEW CHI TIẾT CHO VIDEO TẬP {next_ep} ({novel_title}).
{duration_instruction}

QUY TRÌNH TƯ DUY CỦA BỘ ÓC AI (BẮT BUỘC TUÂN THỦ NGHIÊM NGẶT):
{continuity_block}

2. PHÂN BỔ CỐT TRUYỆN CHUẨN XÁC THEO PHIM & NGUYÊN TÁC (LINH HOẠT TỪ 1 ĐẾN 4-5 CHƯƠNG THEO MẠCH PHIM):
   - Văn bản 'next_novel_context' cung cấp đầy đủ nội dung các chương nguyên tác được AI phân tích nhịp độ hoặc theo người dùng chỉ định (dù là 1-2 chương hay trải dài 4-5 chương nếu tình tiết nhanh):
     * Ví dụ: Tập phim có thể tiếp nối phần dở dang của chương trước (như 50% - 75% chương A), bao quát các chương diễn biến tiếp theo, và dừng lại ở đoạn cao trào nghẹt thở (cliffhanger) ở giữa chương hoặc cuối chương.
   - NGUYÊN TẮC VÀNG VỀ TÌNH TIẾT (CHUẨN 100% THEO PHIM & NGUYÊN TÁC):
     * TUYỆT ĐỐI KHÔNG BỊA ĐẶT TÌNH TIẾT: Phải bám sát chính xác 100% các sự kiện, tên nhân vật, pháp bảo, công pháp và diễn biến có thật trong 'next_novel_context'. Tuyệt đối không dùng văn mẫu sáo rỗng bịa đặt như "tiếng chém giết rền trời" khi nguyên tác không có chiến sự.
     * GIỮ TRỌN VẸN CÁC CUỘC ĐỐI THOẠI QUAN TRỌNG: Trích dẫn trực tiếp các câu thoại đắt giá đặt trong dấu ngoặc kép ("..."), miêu tả ánh mắt, nét mặt thay đổi, biểu cảm vi mô và toan tính tâm lý của từng nhân vật để kịch bản sống động như đang xem phim hoạt hình thực thụ.
     * KHÔNG ĐƯỢC TÓM TẮT LƯỚT BỎ RƠI CỐT TRUYỆN: Kể tuần tự, mạch lạc, phân bổ hợp lý các phân cảnh bao quát toàn bộ nội dung được cấp:
       - Cảnh mở đầu: Tiếp nối điểm dừng và bầu không khí của tập trước, nhân vật bắt đầu hành động.
       - Cảnh diễn biến: Tái hiện sâu sắc các cuộc gặp gỡ, đối thoại, toan tính mưu lược và tương tác giữa các nhân vật.
       - Cảnh cao trào: Đỉnh điểm xung đột, thi triển thần thông, pháp bảo hoặc bẫy rập then chốt.
       - Cảnh kết thúc & Cliffhanger (Các cảnh cuối): KẾT THÚC DỪNG Ở ĐÚNG ĐOẠN CAO TRÀO NGHẸT THỞ (có thể ở giữa chương như tập 189 dừng ngay lúc thả Song Vĩ Xà ám sát, hoặc cuối chương), tạo cảm giác hồi hộp tột độ và kích thích người xem mong chờ tập sau!
     * TUYỆT ĐỐI KHÔNG CHIA MỖI CÂU LÀ MỘT CẢNH! Mỗi phân cảnh là một khối bối cảnh trọn vẹn (khoảng 3 đến 8 câu văn mạch lạc, thời lượng đọc khoảng 20 đến 35 giây).
     * Chỉ chuyển sang phân cảnh mới khi có sự thay đổi rõ ràng về không gian, nhân vật hoặc bước ngoặt hành động.

3. VĂN PHONG REVIEW:
   - {style_instruction}
   - Sử dụng 100% tiếng Việt thuần túy, tuyệt đối KHÔNG để sót bất kỳ chữ Hán nào.

ĐỊNH DẠNG ĐẦU RA JSON BẮT BUỘC:
{{
  "title": "{novel_title} Tập {next_ep}",
  "opening_hook": "Lời chào và mở đầu hấp dẫn, bám sát sự thật tập trước...",
  "scenes": [
    {{
      "scene_id": 1,
      "title": "Tiêu đề phân cảnh ngắn gọn, hấp dẫn",
      "location": "Địa điểm bối cảnh",
      "characters": ["Nhân vật xuất hiện"],
      "action_summary": "Tóm tắt diễn biến hình ảnh",
      "visual_prompt": "Mô tả chi tiết hình ảnh anime 3D cho cảnh này để tìm/cắt ảnh từ phim",
      "voiceover": "Đoạn văn thuyết minh gồm 3 đến 7 câu liền mạch, ngăn cách nhau bằng [0.2]. TUYỆT ĐỐI KHÔNG để [0.5] ở giữa cảnh.",
      "estimated_duration_sec": 25
    }}
  ],
  "closing_outro": "Lời kết review và hẹn tập sau..."
}}"""

        user_payload = {
            "task": "generate_novel_continuation_script",
            "novel_title": novel_title,
            "current_ep": current_ep,
            "next_ep": next_ep,
            "user_prompt_instruction": custom_prompt or "",
            "reference_dialogue_summary": current_summary,
            "next_novel_context": next_novel_context[:65000]
        }
        
        try:
            from capcut_api.api.gui_app import build_ai_translation_config, call_ai_json_object
            ai_config = build_ai_translation_config(item_config={}, purpose="context")
            if ai_config and ai_config.get("enabled"):
                res = call_ai_json_object(ai_config, system_prompt, user_payload, line_count=100)
                if isinstance(res, dict) and (res.get("scenes") or res.get("acts")):
                    def clean_chinese_chars(text: str) -> str:
                        replacements = {
                            "草原": "thảo nguyên",
                            "令牌": "lệnh bài",
                            "大阵": "đại trận",
                            "阵法": "trận pháp",
                            "元婴": "Nguyên Anh",
                            "法宝": "pháp bảo",
                            "神识": "thần thức",
                        }
                        for k, v in replacements.items():
                            text = text.replace(k, v)
                        cleaned = re.sub(r'[\u4e00-\u9fff]+', '', text)
                        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
                        return cleaned

                    parsed_scenes = []
                    raw_scenes = res.get("scenes") or []
                    if not raw_scenes and res.get("acts"):
                        # Fallback nếu model trả về acts
                        for act_idx, act in enumerate(res.get("acts", [])):
                            lines = act.get("voiceover_lines", [])
                            if lines:
                                vo = "\n[0.2]\n".join(clean_chinese_chars(l) for l in lines if clean_chinese_chars(l))
                                raw_scenes.append({
                                    "scene_id": act_idx + 1,
                                    "title": act.get("act_title") or f"Hồi {act_idx + 1}",
                                    "location": "Bối cảnh phim",
                                    "characters": ["Nhân vật"],
                                    "visual_prompt": f"Anime 3D {novel_title}, scene {act_idx + 1}, cinematic 4k",
                                    "voiceover": vo
                                })

                    for idx, sc in enumerate(raw_scenes):
                        vo_raw = clean_chinese_chars(sc.get("voiceover", ""))
                        if vo_raw:
                            # Đảm bảo các câu bên trong dùng [0.2], không dùng [0.5]
                            cleaned_vo = re.sub(r'\[(?:0\.[4-9]|\d+(?:\.\d+)?)\]', '[0.2]', vo_raw)
                            parsed_scenes.append({
                                "scene_id": idx + 1,
                                "title": sc.get("title") or f"Phân Cảnh #{idx + 1}",
                                "location": sc.get("location") or "Bối cảnh phim",
                                "characters": sc.get("characters") or ["Nhân vật"],
                                "action_summary": sc.get("action_summary") or "",
                                "visual_prompt": sc.get("visual_prompt") or f"Anime 3D {novel_title}, scene {idx+1}, cinematic 4k",
                                "voiceover": cleaned_vo,
                                "estimated_duration_sec": sc.get("estimated_duration_sec") or round(len(cleaned_vo.split()) / 3.3, 1)
                            })

                    # Ghép các cảnh lại thành full_plain_text với [0.5] CHỈ GIỮA CÁC CẢNH
                    formatted_script_parts = []
                    opening_hook = clean_chinese_chars(res.get("opening_hook", ""))
                    if opening_hook:
                        formatted_script_parts.append(opening_hook)

                    for sc in parsed_scenes:
                        if sc["voiceover"]:
                            formatted_script_parts.append(sc["voiceover"])

                    closing_outro = clean_chinese_chars(res.get("closing_outro", ""))
                    if closing_outro:
                        formatted_script_parts.append(closing_outro)

                    full_plain_text = "\n[0.5]\n".join(formatted_script_parts)

                    return {
                        "title": res.get("title") or f"{novel_title} Tập {next_ep}",
                        "opening_hook": opening_hook,
                        "scenes": parsed_scenes,
                        "closing_outro": closing_outro,
                        "full_plain_text": full_plain_text,
                        "acts": res.get("acts", []),
                        "total_words": sum(len(p.split()) for p in formatted_script_parts)
                    }
            return self._build_storytelling_from_context(novel_title, next_ep, current_summary, next_novel_context)
        except Exception as e:
            logger.error(f"⚠️ [NOVEL SCRIPT AI ERROR]: {e}", exc_info=True)
            return self._build_storytelling_from_context(novel_title, next_ep, current_summary, next_novel_context)

    async def generate_tts(self, scenes: List[Dict[str, Any]], voice: str = "vi-VN-NamMinhNeural") -> List[Dict[str, Any]]:
        import asyncio

        def clean_vietnamese_text(t: str) -> str:
            if re.search(r'[\u4e00-\u9fff]', t):
                try:
                    url = "https://translate.googleapis.com/translate_a/single"
                    params = {"client": "gtx", "sl": "zh-CN", "tl": "vi", "dt": "t", "q": t}
                    r = requests.get(url, params=params, timeout=5)
                    if r.status_code == 200:
                        res = r.json()
                        trans = "".join(s[0] for s in res[0] if s and s[0]).strip()
                        if trans:
                            return trans
                except Exception:
                    pass
            return t

        async def process_one_scene(idx: int, scene: Dict[str, Any]) -> Dict[str, Any]:
            raw_text = scene.get("voiceover", "").strip()
            if not raw_text:
                return dict(scene, duration=3.0)
            
            text = clean_vietnamese_text(raw_text)
            # Làm sạch thẻ pause [0.2] thành dấu ngắt câu tự nhiên khi đọc TTS
            tts_text = re.sub(r'\[\d+(?:\.\d+)?\]', '...', text).strip()
            out_file = self.audio_output_dir / f"scene_{idx+1:02d}.mp3"
            dur = max(2.5, len(tts_text) * 0.08)
            
            try:
                # Nếu text vẫn còn tiếng Trung, dùng voice tiếng Trung hoặc skip
                cur_voice = "zh-CN-YunxiNeural" if re.search(r'[\u4e00-\u9fff]', tts_text) else voice
                comm = edge_tts.Communicate(tts_text, cur_voice, rate="+10%")
                await comm.save(str(out_file))
                if out_file.exists() and out_file.stat().st_size > 500:
                    dur = max(2.0, out_file.stat().st_size / 5500.0)
            except Exception:
                pass
            
            sc = dict(scene)
            sc["voiceover"] = text
            if out_file.exists() and out_file.stat().st_size > 500:
                sc["audio_file"] = str(out_file.resolve())
            sc["duration"] = round(dur, 2)
            return sc

        tasks = [process_one_scene(idx, sc) for idx, sc in enumerate(scenes)]
        results = await asyncio.gather(*tasks)
        return results

    def build_capcut_draft(self, project_name: str, scenes: List[Dict[str, Any]], image_paths: Optional[List[str]] = None, canvas_ratio: str = "16:9") -> str:
        draft_id = str(uuid.uuid4()).upper()
        clean_name = "".join(c for c in project_name if c.isalnum() or c in (" ", "_", "-")).strip()
        project_folder = self.capcut_drafts_dir / f"{clean_name}_{int(time.time())}"
        project_folder.mkdir(parents=True, exist_ok=True)

        current_time_us = 0
        materials = {"audios": [], "videos": [], "texts": []}
        audio_segs, video_segs, text_segs = [], [], []

        width = 1080 if canvas_ratio == "9:16" else 1920
        height = 1920 if canvas_ratio == "9:16" else 1080

        for idx, scene in enumerate(scenes):
            dur_us = int(scene.get("duration", 3.5) * 1_000_000)
            text = scene.get("voiceover", "")
            audio_path = scene.get("audio_file", "")
            img_path = (image_paths[idx % len(image_paths)] if image_paths else "") or scene.get("image_path", "")

            # Audio
            if audio_path and os.path.exists(audio_path):
                aid = str(uuid.uuid4())
                materials["audios"].append({"id": aid, "type": "extract_music", "path": str(Path(audio_path).resolve()), "duration": dur_us, "name": f"VO_{idx+1}.mp3"})
                audio_segs.append({"id": str(uuid.uuid4()), "material_id": aid, "target_timerange": {"duration": dur_us, "start": current_time_us}, "source_timerange": {"duration": dur_us, "start": 0}, "speed": 1.0, "volume": 1.0})

            # Image/Video
            if img_path and os.path.exists(img_path):
                vid = str(uuid.uuid4())
                is_video = Path(img_path).suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm")
                materials["videos"].append({
                    "id": vid,
                    "type": "video" if is_video else "photo",
                    "path": str(Path(img_path).resolve()),
                    "duration": dur_us,
                    "width": width,
                    "height": height,
                    "material_name": f"Media_{idx+1}"
                })
                source_start = (idx * 4_000_000) if is_video else 0
                video_segs.append({
                    "id": str(uuid.uuid4()),
                    "material_id": vid,
                    "target_timerange": {"duration": dur_us, "start": current_time_us},
                    "source_timerange": {"duration": dur_us, "start": source_start},
                    "clip": {"scale": {"x": 1.05, "y": 1.05}, "transform": {"x": 0.0, "y": 0.0}}
                })

            # Subtitle (Chuẩn thẩm mỹ: chữ vàng kim viền đen, font nhỏ 5.5, căn giữa ở đáy)
            if text:
                tid = str(uuid.uuid4())
                text_json = {
                    "text": text,
                    "styles": [{
                        "fill": {
                            "alpha": 1.0,
                            "content": {
                                "render_type": "solid",
                                "solid": {"color": [1.0, 0.92, 0.15]}
                            }
                        },
                        "size": 5.5,
                        "bold": True
                    }]
                }
                materials["texts"].append({
                    "id": tid,
                    "type": "subtitle",
                    "content": json.dumps(text_json, ensure_ascii=False),
                    "font_path": "",
                    "font_size": 5.5,
                    "text_color": "#FFE81F",
                    "border_color": "#000000",
                    "border_width": 0.08
                })
                text_segs.append({
                    "id": str(uuid.uuid4()),
                    "material_id": tid,
                    "target_timerange": {"duration": dur_us, "start": current_time_us},
                    "clip": {"transform": {"x": 0.0, "y": -0.78}}
                })

            current_time_us += dur_us

        draft_content = {
            "id": draft_id, "version": 3000000, "duration": current_time_us, "fps": 30.0, "ratio": canvas_ratio,
            "resolution": {"width": width, "height": height}, "materials": materials,
            "tracks": [{"id": str(uuid.uuid4()), "type": "video", "segments": video_segs}, {"id": str(uuid.uuid4()), "type": "audio", "segments": audio_segs}, {"id": str(uuid.uuid4()), "type": "text", "segments": text_segs}]
        }
        (project_folder / "draft_content.json").write_text(json.dumps(draft_content, ensure_ascii=False, indent=2), encoding="utf-8")
        (project_folder / "draft_meta_info.json").write_text(json.dumps({"draft_id": draft_id, "draft_name": project_name, "draft_timeline_dur": current_time_us, "tm_draft_create": int(time.time() * 1000), "tm_draft_modified": int(time.time() * 1000)}, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(project_folder.resolve())

    def export_plain_text_script(self, script: Dict[str, Any], out_txt_path: Path) -> str:
        """Xuất kịch bản: mỗi câu/cụm từ 1 dòng kèm ký hiệu khoảng nghỉ như [0.2], [0.3], [0.5]."""
        from capcut_api.ai.subtitle_chunker import chunker as ai_chunker
        scenes = script.get("scenes", [])
        output_lines = []

        def split_into_sentences_with_pauses(text: str) -> List[str]:
            # Dùng AI Chunker tách câu dài thành các cụm 4-6 từ ngắn gọn
            chunks = ai_chunker.chunk_text(text)
            if not chunks:
                return []

            formatted = []
            for i, chunk_s in enumerate(chunks):
                clean_s = re.sub(r'\[\d+(?:\.\d+)?\]', '', chunk_s).strip()
                if not clean_s:
                    continue
                formatted.append(clean_s)
                # Khoảng nghỉ: [0.5] cho kết thúc đoạn, [0.2] cho giữa đoạn
                pause = "[0.5]" if i == len(chunks) - 1 else "[0.2]"
                formatted.append(pause)
            return formatted

        for sc in scenes:
            vo = sc.get("voiceover", "").strip()
            if vo:
                sent_lines = split_into_sentences_with_pauses(vo)
                output_lines.extend(sent_lines)
                output_lines.append("")

        full_text = "\n".join(output_lines).strip()
        out_txt_path.write_text(full_text, encoding="utf-8")
        return str(out_txt_path.resolve())

    def export_srt_file(self, scenes: List[Dict[str, Any]], out_srt_path: Path) -> str:
        """Tính toán timestamp dựa trên độ dài audio TTS thực tế và xuất file .srt."""
        srt_lines = []
        cur_sec = 0.0
        
        def format_time(seconds: float) -> str:
            millis = int((seconds - int(seconds)) * 1000)
            mins, secs = divmod(int(seconds), 60)
            hrs, mins = divmod(mins, 60)
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"

        for idx, scene in enumerate(scenes):
            dur = float(scene.get("duration", 4.0))
            start_t = format_time(cur_sec)
            end_t = format_time(cur_sec + dur)
            text = scene.get("voiceover", "").strip()
            
            srt_lines.append(f"{idx+1}\n{start_t} --> {end_t}\n{text}\n")
            cur_sec += dur

        out_srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        return str(out_srt_path.resolve())

    def run_full_novel_recap(
        self,
        current_episode_num: int = 1,
        novel_id: str = "xianni",
        voice: str = "vi-VN-NamMinhNeural",
        tts_speed: float = 1.1,
        canvas_ratio: str = "16:9",
        scenes: Optional[List[Dict[str, Any]]] = None,
        media_paths: Optional[List[str]] = None,
        image_paths: Optional[List[str]] = None,
        transcript_text: str = "",
        prompt: Optional[str] = None,
        custom_prompt: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        import asyncio
        active_prompt = custom_prompt or prompt
        final_media = media_paths or image_paths or []

        all_novels = self.repo.list_all_novels()
        novel_obj = next((n for n in all_novels if n["id"] == novel_id), None)
        novel_title = novel_obj["name"] if novel_obj else "Phàm Nhân Tu Tiên"

        user_script_text = kwargs.get("script_text") or kwargs.get("novel_script_text") or ""
        
        # BƯỚC 1: Sinh kịch bản văn bản thuần túy (.txt) hoặc dùng kịch bản người dùng đã sửa
        if user_script_text and user_script_text.strip():
            lines = [l.strip() for l in user_script_text.splitlines() if l.strip()]
            parsed_scenes = []
            current_vo_lines = []

            for l in lines:
                if re.match(r'^\[0\.5\]$', l):
                    if current_vo_lines:
                        vo_text = " ".join(current_vo_lines).strip()
                        if vo_text:
                            parsed_scenes.append({
                                "scene_id": len(parsed_scenes) + 1,
                                "voiceover": vo_text,
                                "visual_prompt": f"Anime visual for {novel_title}, scene {len(parsed_scenes)+1}",
                                "animation": ["Zoom In", "Zoom Out", "Pan Left", "Pan Right"][len(parsed_scenes) % 4]
                            })
                        current_vo_lines = []
                elif not re.match(r'^\[\d+(?:\.\d+)?\]$', l):
                    clean_l = re.sub(r'\[\d+(?:\.\d+)?\]', '', l).strip()
                    if clean_l:
                        current_vo_lines.append(clean_l)

            if current_vo_lines:
                vo_text = " ".join(current_vo_lines).strip()
                if vo_text:
                    parsed_scenes.append({
                        "scene_id": len(parsed_scenes) + 1,
                        "voiceover": vo_text,
                        "visual_prompt": f"Anime visual for {novel_title}, scene {len(parsed_scenes)+1}",
                        "animation": ["Zoom In", "Zoom Out", "Pan Left", "Pan Right"][len(parsed_scenes) % 4]
                    })

            if not parsed_scenes:
                raw_paragraphs = [p.strip() for p in user_script_text.split("\n\n") if p.strip()]
                for idx, p in enumerate(raw_paragraphs):
                    vo_lines = [line.strip() for line in p.splitlines() if line.strip() and not re.match(r'^\[\d+(?:\.\d+)?\]$', line.strip())]
                    clean_vo = " ".join(vo_lines).strip()
                    if clean_vo:
                        parsed_scenes.append({
                            "scene_id": idx + 1,
                            "voiceover": clean_vo,
                            "visual_prompt": f"Anime visual for {novel_title}, scene {idx+1}",
                            "animation": ["Zoom In", "Zoom Out", "Pan Left", "Pan Right"][idx % 4]
                        })

            raw_scenes = parsed_scenes if parsed_scenes else (scenes or [])
            script = {"scenes": raw_scenes, "title": f"{novel_title} Tập {current_episode_num + 1}"}
        elif not scenes:
            context = self.get_dynamic_novel_context(novel_id, transcript_text, active_prompt, current_episode_num=current_episode_num)
            curr_summary = transcript_text[:1500] if transcript_text else ""
            script = self.generate_script(curr_summary, context, current_episode_num, current_episode_num + 1, novel_title=novel_title, custom_prompt=active_prompt)
            raw_scenes = script.get("scenes", [])
        else:
            script = {"scenes": scenes, "title": f"{novel_title} Tập {current_episode_num + 1}"}
            raw_scenes = scenes

        # BƯỚC 1 - B5: CHẠY QUA NOVEL VIDEO PIPELINE CHUYÊN BIỆT
        from capcut_api.ai.novel_video_pipeline import NovelVideoPipeline
        pipeline = NovelVideoPipeline(novel_id=novel_id)

        clean_novel_name = "".join(c for c in novel_title if c.isalnum() or c in (" ", "_", "-")).strip()
        project_name = f"{clean_novel_name}_Tap_{current_episode_num + 1}_ThuyetMinh"

        # Tự động lấy kịch bản từ user hoặc từ AI đã sinh
        if user_script_text and user_script_text.strip():
            final_script_text = user_script_text.strip()
        elif script and script.get("scenes"):
            # Chuyển scenes sang text có thẻ ngắt nghỉ
            temp_lines = []
            for sc in script.get("scenes", []):
                vo = sc.get("voiceover", "").strip()
                if vo:
                    temp_lines.append(vo)
                    temp_lines.append("[0.5]")
            final_script_text = "\n".join(temp_lines)
        else:
            final_script_text = transcript_text

        # Tốc độ đọc: ưu tiên 1.2x theo yêu cầu người dùng
        chosen_speed = float(tts_speed or 1.2)
        if chosen_speed < 0.5 or chosen_speed > 3.0:
            chosen_speed = 1.2

        # Tên giọng đọc NghiTTS chuẩn xác
        voice_arg = kwargs.get("voice_name") or voice or "Ngọc Huyền (mới)"
        valid_nghitts = ["Ngọc Huyền (mới)", "Nam Miền Nam", "Nữ Miền Nam"]
        matched_voice = next((v for v in valid_nghitts if v.lower() in voice_arg.lower()), None)
        chosen_voice = matched_voice or "Ngọc Huyền (mới)"

        # Chạy toàn bộ 5 bước của Pipeline
        pipeline_res = pipeline.run_full_pipeline(
            script_text=final_script_text,
            project_name=project_name,
            voice_name=chosen_voice,
            speed=chosen_speed,
            media_paths=final_media,
            canvas_ratio=canvas_ratio,
            auto_open_capcut=kwargs.get("auto_open_capcut", True)
        )

        txt_file = Path(pipeline_res["draft_folder"]) / f"{project_name}_kich_ban.txt"

        return {
            "success": True,
            "project_name": project_name,
            "draft_folder": pipeline_res["draft_folder"],
            "txt_file": str(txt_file.resolve()) if txt_file.exists() else "",
            "srt_file": pipeline_res.get("srt_file", ""),
            "master_mp3": pipeline_res.get("master_mp3", ""),
            "script": script,
            "scenes_count": pipeline_res.get("scenes_count", 0),
            "sentences_count": pipeline_res.get("sentences_count", 0),
            "total_duration_sec": pipeline_res.get("total_duration_sec", 0.0),
            "capcut_status": pipeline_res.get("capcut_status", {})
        }
