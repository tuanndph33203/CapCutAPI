import os
import sys
import re
import json
import uuid
import time
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from openai import OpenAI
import edge_tts
import requests
from bs4 import BeautifulSoup
from capcut_api.ai.visuals_dataset_manager import VisualsDatasetManager

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
        target = self.custom_novels_dir / novel_id
        if target.exists() and target.is_dir():
            ch_dir = target / "chapters"
            return ch_dir if ch_dir.exists() else target
            
        target_harness = self.harness_novels_dir / novel_id
        if target_harness.exists() and target_harness.is_dir():
            ch_dir = target_harness / "reference" / "chapters"
            return ch_dir if ch_dir.exists() else target_harness

        if novel_id in ("xianni", "仙逆"):
            p = self.harness_novels_dir / "仙逆" / "reference" / "chapters"
            if p.exists():
                return p
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

        self.audio_output_dir = self.root_dir / "outputs" / "novel_audio"
        self.audio_output_dir.mkdir(parents=True, exist_ok=True)

        self.client = OpenAI(base_url="http://localhost:20128/v1", api_key="sk-d13e798ca7a8589d-jfr5u9-d6a964f4", max_retries=0, timeout=2.5)

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

    def get_dynamic_novel_context(self, novel_id: str, transcript_text: str = "", prompt: Optional[str] = None, current_episode_num: int = 1, max_chars: int = 4000) -> str:
        """Đọc bối cảnh chương truyện thông minh dựa trên từ khóa tiếng Việt/Hán Việt, prompt hoặc số tập/chương."""
        chapters = self.repo.list_novel_chapters(novel_id)
        if not chapters:
            return ""

        # Từ điển ánh xạ từ khóa tiếng Việt sang chữ Hán trong nguyên tác
        vi_to_zh_keywords = {
            "nam lũng hầu": "南陇",
            "nam lũng": "南陇",
            "lạc vân tông": "落云",
            "lạc vân": "落云",
            "mộ bái linh": "慕沛",
            "mộ phải linh": "慕沛",
            "trụy ma cốc": "坠魔",
            "thiên tinh chân nhân": "天晶",
            "hỏa long đồng tử": "火龙",
            "huyết sắc thí luyện": "血色",
            "thất huyền môn": "七玄门",
            "mặc đại phu": "墨大夫",
            "hoàng phong cốc": "黄枫",
            "hư thiên điện": "虚天殿",
            "cực âm tổ sư": "极阴",
            "cực âm": "极阴",
            "man hồ tử": "蛮胡子",
            "vương lâm": "王林",
            "thiết trụ": "铁柱",
            "tư đồ nam": "司徒南",
            "hằng nhạc phái": "恒岳派"
        }

        matched_idx = -1
        search_target_text = f"{transcript_text} {prompt or ''}".lower()

        # 1. Tìm theo từ khóa Hán Việt chuyển ngữ nếu có trong transcript hoặc prompt
        if search_target_text.strip():
            matched_zh_keys = []
            for vi_k, zh_k in vi_to_zh_keywords.items():
                if vi_k in search_target_text:
                    matched_zh_keys.append(zh_k)

            if matched_zh_keys:
                best_score = 0
                for idx, ch in enumerate(chapters):
                    score = 0
                    title = ch.get("title", "")
                    for zh in matched_zh_keys:
                        if zh in title:
                            score += 10
                    if score > best_score:
                        best_score = score
                        matched_idx = idx

        # 2. Hoặc tìm số chương được đề cập rõ ràng trong prompt (ví dụ: "chương 682")
        if matched_idx == -1 and prompt:
            m = re.search(r'(?:chương|chuong|chapter|ch)\s*(\d+)', prompt, re.IGNORECASE)
            if m:
                target_num = int(m.group(1))
                for idx, ch in enumerate(chapters):
                    if ch.get("chapter_num") == target_num or ch.get("index") == target_num:
                        matched_idx = idx
                        break

        # 3. Hoặc ước lượng mốc chương cho Anime 3D Phàm Nhân Tu Tiên
        if matched_idx == -1:
            if novel_id == "Pham nhan tu tien" and current_episode_num >= 180:
                # Anime Phàm Nhân Tu Tiên tập 185-186 tương ứng với Chương 680-685 (Tái kiến Nam Lũng Hầu)
                target_ch = 682 if current_episode_num in (185, 186) else int(current_episode_num * 3.65)
                for idx, ch in enumerate(chapters):
                    if ch.get("chapter_num") == target_ch or ch.get("index") == target_ch:
                        matched_idx = idx
                        break
            elif current_episode_num and current_episode_num > 1:
                for idx, ch in enumerate(chapters):
                    if ch.get("chapter_num") == current_episode_num or ch.get("index") == current_episode_num:
                        matched_idx = idx
                        break

        if matched_idx == -1:
            matched_idx = 0

        # Lấy 3 đến 5 chương kế tiếp từ điểm mốc
        start_i = matched_idx
        end_i = min(len(chapters), start_i + 4)
        
        texts = []
        for ch in chapters[start_i:end_i]:
            res = self.repo.get_chapter_content(novel_id, ch["filename"])
            if res.get("success"):
                texts.append(f"=== 【{ch['title']}】 ===\n{res.get('content', '')[:1500]}\n")
        
        return "\n".join(texts)

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

    def generate_script(self, current_summary: str, next_novel_context: str, current_ep: int, next_ep: int, novel_title: str = "Phàm Nhân Tu Tiên", custom_prompt: Optional[str] = None) -> Dict[str, Any]:
        # 1. ƯU TIÊN HÀNG ĐẦU: Tìm kiếm kịch bản review mẫu chuẩn chất lượng cao trong Downloads hoặc Kho Data
        ref_sentences = self._find_reference_review_script(self.novel_id, next_ep)
        if ref_sentences:
            scenes = []
            animations = ["Zoom In", "Zoom Out", "Pan Left", "Pan Right"]
            for idx, s in enumerate(ref_sentences):
                clean_s = re.sub(r'\s+', ' ', s).strip()
                if not clean_s:
                    continue
                scenes.append({
                    "scene_id": idx + 1,
                    "voiceover": clean_s,
                    "visual_prompt": f"Anime {novel_title}, dramatic review scene {idx + 1}, cinematic lighting",
                    "animation": animations[idx % len(animations)]
                })
            if scenes:
                return {
                    "title": f"{novel_title} Tập {next_ep}",
                    "opening_hook": scenes[0]["voiceover"],
                    "scenes": scenes,
                    "closing_outro": scenes[-1]["voiceover"]
                }

        system_prompt = custom_prompt or f"""Bạn là Biên kịch Review/Thuyết minh Anime Tu Tiên chuyên nghiệp (Top YouTube Reviewer hàng triệu view).
Hãy viết KỊCH BẢN THUYẾT MINH & KỂ CHUYỆN CHI TIẾT cho video tập {next_ep} dựa trên nguyên tác chương truyện được cung cấp.

YÊU CẦU VĂN PHONG VÀ CẤU TRÚC:
1. MỞ ĐẦU (opening_hook): Bắt đầu đúng mẫu: "{novel_title} tập {next_ep}. Ở cuối tập trước, [Tóm tắt ngắn gọn cao trào tập trước]. Trong tập này chúng ta cùng xem tiếp những diễn biến tiếp theo nha."
2. THÂN BÀI (scenes): Kể lại chi tiết, lôi cuốn toàn bộ các diễn biến, đối thoại, tâm lý nhân vật, chiêu thức, âm mưu trận chiến từ nguyên tác chương truyện. Chia thành các phân đoạn kể chuyện (tối thiểu 15-25 đoạn voiceover liền mạch, mỗi đoạn 2-3 câu vừa vặn để làm phụ đề và lồng tiếng TTS).
   Mỗi scene gồm:
   - "scene_id": số thứ tự (1, 2, 3...)
   - "voiceover": Lời kể chuyện tiếng Việt tự nhiên, hấp dẫn, đúng thuật ngữ tu tiên kiếm hiệp.
   - "visual_prompt": Gợi ý cảnh phim tiếng Anh tương ứng để tìm ảnh/video.
   - "animation": Hiệu ứng chuyển động (Zoom In, Zoom Out, Pan Left, Pan Right).
3. KẾT BÀI (closing_outro): Kết thúc đúng mẫu: "Tới đây cũng tạm thời kết thúc nội dung của tập hôm nay rồi. Cảm ơn các bạn đã xem hết video. Nếu muốn mình ra thêm tập {next_ep + 1} thì đừng quên để lại ý kiến dưới phần bình luận nhé. Còn bây giờ xin chào và hẹn gặp lại."

Trả về ĐÚNG CẤU TRÚC JSON thuần túy:
{{
  "title": "{novel_title} Tập {next_ep}",
  "opening_hook": "...",
  "scenes": [
    {{"scene_id": 1, "voiceover": "...", "visual_prompt": "...", "animation": "Zoom In"}},
    ...
  ],
  "closing_outro": "..."
}}"""

        user_prompt = f"TẬP HIỆN TẠI (TẬP {current_ep}):\n{current_summary}\n\nDIỄN BIẾN NGUYÊN TÁC CÁC CHƯƠNG TIẾP THEO (TẬP {next_ep}):\n{next_novel_context}"
        
        try:
            resp = self.client.chat.completions.create(
                model="ag/gemini-3.7-flash-high",
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                response_format={"type": "json_object"},
                temperature=0.7,
                timeout=3.0
            )
            content = resp.choices[0].message.content.strip()
            parsed = json.loads(content)
            if parsed.get("scenes") and len(parsed.get("scenes", [])) >= 5:
                return parsed
            return self._build_storytelling_from_context(novel_title, next_ep, current_summary, next_novel_context)
        except Exception:
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
            img_path = image_paths[idx] if (image_paths and idx < len(image_paths)) else scene.get("image_path", "")

            # Audio
            if audio_path and os.path.exists(audio_path):
                aid = str(uuid.uuid4())
                materials["audios"].append({"id": aid, "type": "extract_music", "path": str(Path(audio_path).resolve()), "duration": dur_us, "name": f"VO_{idx+1}.mp3"})
                audio_segs.append({"id": str(uuid.uuid4()), "material_id": aid, "target_timerange": {"duration": dur_us, "start": current_time_us}, "source_timerange": {"duration": dur_us, "start": 0}, "speed": 1.0, "volume": 1.0})

            # Image/Video
            if img_path and os.path.exists(img_path):
                vid = str(uuid.uuid4())
                materials["videos"].append({"id": vid, "type": "photo", "path": str(Path(img_path).resolve()), "duration": dur_us, "width": width, "height": height, "material_name": f"Media_{idx+1}"})
                video_segs.append({"id": str(uuid.uuid4()), "material_id": vid, "target_timerange": {"duration": dur_us, "start": current_time_us}, "source_timerange": {"duration": dur_us, "start": 0}, "clip": {"scale": {"x": 1.05, "y": 1.05}, "transform": {"x": 0.0, "y": 0.0}}})

            # Subtitle
            if text:
                tid = str(uuid.uuid4())
                text_json = {"text": text, "styles": [{"fill": {"alpha": 1.0, "content": {"render_type": "solid", "solid": {"color": [1.0, 0.9, 0.2]}}}, "size": 11.0, "bold": True}]}
                materials["texts"].append({"id": tid, "type": "subtitle", "content": json.dumps(text_json, ensure_ascii=False), "font_path": "", "font_size": 11.0, "text_color": "#FFE500", "border_color": "#000000", "border_width": 2.0})
                text_segs.append({"id": str(uuid.uuid4()), "material_id": tid, "target_timerange": {"duration": dur_us, "start": current_time_us}, "clip": {"transform": {"x": 0.0, "y": -0.75}}})

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
        """Xuất kịch bản: mỗi câu 1 dòng kèm ký hiệu khoảng nghỉ như [0.2], [0.3], [0.5]."""
        scenes = script.get("scenes", [])
        output_lines = []

        def split_into_sentences_with_pauses(text: str) -> List[str]:
            raw_sents = [s.strip() for s in re.split(r'([\.\!\?…]+)', text) if s.strip()]
            sentences = []
            cur = ""
            for s in raw_sents:
                cur += s
                if re.match(r'[\.\!\?…]+', s):
                    sentences.append(cur.strip())
                    cur = ""
            if cur.strip():
                sentences.append(cur.strip())

            formatted = []
            for i, sent in enumerate(sentences):
                clean_s = re.sub(r'\[\d+(?:\.\d+)?\]', '', sent).strip()
                if not clean_s:
                    continue
                # Câu văn trên 1 dòng riêng
                formatted.append(clean_s)
                # Khoảng nghỉ trên 1 dòng riêng: [0.2] cho câu giữa đoạn, [0.5] cho câu kết thúc đoạn
                pause = "[0.5]" if i == len(sentences) - 1 else "[0.2]"
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
            raw_paragraphs = [p.strip() for p in user_script_text.split("\n\n") if p.strip()]
            parsed_scenes = []
            for idx, p in enumerate(raw_paragraphs):
                # Lấy các dòng câu thoại bỏ qua thẻ [0.2], [0.5]
                vo_lines = [line.strip() for line in p.splitlines() if line.strip() and not re.match(r'^\[\d+(?:\.\d+)?\]$', line.strip())]
                clean_vo = " ".join(vo_lines).strip()
                if clean_vo:
                    parsed_scenes.append({
                        "scene_id": idx + 1,
                        "voiceover": clean_vo,
                        "visual_prompt": f"Anime visual for {novel_title}, scene {idx+1}",
                        "animation": ["Zoom In", "Zoom Out", "Pan Left", "Pan Right"][idx % 4]
                    })
            if parsed_scenes:
                raw_scenes = parsed_scenes
                script = {"scenes": raw_scenes, "title": f"{novel_title} Tập {current_episode_num + 1}"}
            else:
                raw_scenes = scenes or []
                script = {"scenes": raw_scenes, "title": f"{novel_title} Tập {current_episode_num + 1}"}
        elif not scenes:
            context = self.get_dynamic_novel_context(novel_id, transcript_text, active_prompt, current_episode_num=current_episode_num)
            curr_summary = transcript_text[:1500] if transcript_text else ""
            script = self.generate_script(curr_summary, context, current_episode_num, current_episode_num + 1, novel_title=novel_title, custom_prompt=active_prompt)
            raw_scenes = script.get("scenes", [])
        else:
            script = {"scenes": scenes, "title": f"{novel_title} Tập {current_episode_num + 1}"}
            raw_scenes = scenes

        # BƯỚC 2: Sinh âm thanh từ TTS
        scenes_with_audio = asyncio.run(self.generate_tts(raw_scenes, voice=voice))

        # Tự động map ảnh từ Visuals Dataset nếu chưa truyền media thủ công
        if not final_media:
            final_media = self.visuals_mgr.match_visuals_for_scenes(scenes_with_audio, novel_id)

        clean_novel_name = "".join(c for c in novel_title if c.isalnum() or c in (" ", "_", "-")).strip()
        project_name = f"{clean_novel_name}_Tap_{current_episode_num + 1}_ThuyetMinh"
        draft_folder = self.build_capcut_draft(project_name, scenes_with_audio, final_media, canvas_ratio=canvas_ratio)

        # Xuất file Kịch Bản Văn Bản thuần túy (.txt)
        txt_file = Path(draft_folder) / f"{project_name}_kich_ban.txt"
        if user_script_text and user_script_text.strip():
            txt_file.write_text(user_script_text.strip(), encoding="utf-8")
        else:
            self.export_plain_text_script(script, txt_file)

        # BƯỚC 3: Tính toán timestamp từ audio TTS thực tế và xuất file phụ đề chuẩn (.srt)
        srt_file = Path(draft_folder) / f"{project_name}.srt"
        self.export_srt_file(scenes_with_audio, srt_file)

        return {
            "success": True,
            "project_name": project_name,
            "draft_folder": draft_folder,
            "txt_file": str(txt_file.resolve()),
            "srt_file": str(srt_file.resolve()),
            "script": script,
            "scenes": scenes_with_audio
        }
