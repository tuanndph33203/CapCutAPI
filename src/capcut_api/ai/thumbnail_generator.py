"""
Auto Thumbnail 3D Generator for Novel Recap Video Production
============================================================
Creates cinematic, high-retention 16:9 (1280x720) YouTube thumbnails:
1. Selects or takes a dramatic keyframe from novel anime scenes.
2. Applies cinematic color enhancement & vignette / bottom-top gradient overlay.
3. Renders prominent 3D text styling (Golden main title, 3D shadow layers, bold black stroke).
4. Renders an eye-catching crimson/gold episode badge (e.g., "TẬP 192").
5. Exports ready-to-publish 'thumbnail.jpg' (1280x720).
"""

import os
import sys
import math
from pathlib import Path
from typing import Optional, List, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


class ThumbnailGenerator:
    """Tự động tạo ảnh bìa Thumbnail YouTube 3D chuẩn 1280x720 từ ảnh phân cảnh tập phim."""

    def __init__(self):
        self.width = 1280
        self.height = 720

    def _get_font(self, size: int, bold: bool = True) -> ImageFont.ImageFont:
        """Tìm font chữ hỗ trợ tiếng Việt trên Windows (Arial, Segoe UI, Tahoma)."""
        font_names = [
            "arialbd.ttf" if bold else "arial.ttf",
            "segoeuib.ttf" if bold else "segoeui.ttf",
            "tahomabd.ttf" if bold else "tahoma.ttf",
            "arial.ttf",
            "msgothic.ttc"
        ]
        win_fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        for name in font_names:
            font_path = win_fonts_dir / name
            if font_path.exists():
                try:
                    return ImageFont.truetype(str(font_path), size)
                except Exception:
                    pass
        return ImageFont.load_default()

    def generate_thumbnail(
        self,
        base_image_path: Optional[str] = None,
        novel_title: str = "Phàm Nhân Tu Tiên",
        episode_label: str = "TẬP 192",
        subtitle_highlight: Optional[str] = "ĐẠI CHIẾN ĐỈNH CAO",
        output_path: Optional[str] = None
    ) -> str:
        """
        Sinh ảnh Thumbnail 1280x720 chuẩn YouTube.
        """
        # 1. Tạo ảnh nền
        if base_image_path and os.path.exists(base_image_path):
            try:
                img = Image.open(base_image_path).convert("RGB")
                # Scale & Center Crop to 1280x720
                img_ratio = img.width / img.height
                target_ratio = self.width / self.height

                if img_ratio > target_ratio:
                    new_w = int(self.height * img_ratio)
                    img = img.resize((new_w, self.height), Image.Resampling.LANCZOS)
                    left = (new_w - self.width) // 2
                    img = img.crop((left, 0, left + self.width, self.height))
                else:
                    new_h = int(self.width / img_ratio)
                    img = img.resize((self.width, new_h), Image.Resampling.LANCZOS)
                    top = (new_h - self.height) // 2
                    img = img.crop((0, top, self.width, top + self.height))

                # Tăng tương phản và độ rực rỡ nhẹ cho ảnh thêm sống động
                img = ImageEnhance.Color(img).enhance(1.25)
                img = ImageEnhance.Contrast(img).enhance(1.15)
            except Exception:
                img = self._create_gradient_background()
        else:
            img = self._create_gradient_background()

        # 2. Tạo lớp phủ gradient điện ảnh (Cinematic Vignette)
        overlay = Image.new("RGBA", (self.width, self.height), (0, 0, 0, 0))
        draw_ov = ImageDraw.Draw(overlay)

        # Gradient bóng đen ở dưới (cho phần chữ chính dễ đọc)
        for y in range(self.height // 2, self.height):
            alpha = int(220 * ((y - self.height // 2) / (self.height // 2)) ** 1.5)
            draw_ov.line([(0, y), (self.width, y)], fill=(0, 0, 0, alpha))

        # Gradient nhẹ ở trên đỉnh (cho huy hiệu tập)
        for y in range(0, self.height // 4):
            alpha = int(140 * (1.0 - y / (self.height // 4)))
            draw_ov.line([(0, y), (self.width, y)], fill=(0, 0, 0, alpha))

        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

        # 3. Vẽ Huy hiệu TẬP (Episode Badge) góc trên bên trái
        badge_font = self._get_font(size=44, bold=True)
        badge_text = episode_label.upper().strip()
        badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
        bw = badge_bbox[2] - badge_bbox[0]
        bh = badge_bbox[3] - badge_bbox[1]

        pad_x, pad_y = 30, 16
        bx0, by0 = 40, 36
        bx1, by1 = bx0 + bw + pad_x * 2, by0 + bh + pad_y * 2

        # Đổ bóng huy hiệu
        draw.rounded_rectangle([bx0 + 4, by0 + 4, bx1 + 4, by1 + 4], radius=16, fill=(0, 0, 0, 180))
        # Nền đỏ rượu vang kịch tính (Crimson)
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=16, fill=(210, 20, 20), outline=(255, 215, 0), width=3)
        # Chữ trắng vàng nổi bật
        draw.text((bx0 + pad_x, by0 + pad_y - 4), badge_text, font=badge_font, fill=(255, 255, 255))

        # 4. Vẽ Tiêu đề chính 3D nổi bật ở nửa dưới
        title_font = self._get_font(size=72, bold=True)
        title_text = novel_title.upper().strip()
        title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
        tw = title_bbox[2] - title_bbox[0]
        th = title_bbox[3] - title_bbox[1]

        # Căn giữa theo chiều ngang hoặc lề trái
        tx = 45
        ty = self.height - th - (140 if subtitle_highlight else 70)

        # Vẽ bóng 3D nhiều lớp (3D Shadow effect)
        for offset in range(8, 0, -1):
            draw.text((tx + offset, ty + offset), title_text, font=title_font, fill=(15, 15, 15))

        # Vẽ viền đen dày (Stroke)
        stroke_width = 5
        for sx in range(-stroke_width, stroke_width + 1):
            for sy in range(-stroke_width, stroke_width + 1):
                if sx * sx + sy * sy <= stroke_width * stroke_width:
                    draw.text((tx + sx, ty + sy), title_text, font=title_font, fill=(0, 0, 0))

        # Vẽ màu chữ chính: Vàng hoàng kim #FFE500
        draw.text((tx, ty), title_text, font=title_font, fill=(255, 230, 0))

        # 5. Vẽ dòng phụ đề giật gân (Subtitle Highlight) nếu có
        if subtitle_highlight:
            sub_font = self._get_font(size=46, bold=True)
            sub_text = subtitle_highlight.upper().strip()
            sub_bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
            sw = sub_bbox[2] - sub_bbox[0]
            sh = sub_bbox[3] - sub_bbox[1]
            sx_pos = 45
            sy_pos = ty + th + 24

            # Nền chữ nhật đen mờ sau dòng highlight
            draw.rectangle([sx_pos - 10, sy_pos - 6, sx_pos + sw + 16, sy_pos + sh + 10], fill=(0, 0, 0, 190))
            # Viền đen dày & chữ trắng/đỏ rực rỡ
            for dx in [-2, 0, 2]:
                for dy in [-2, 0, 2]:
                    draw.text((sx_pos + dx, sy_pos + dy), sub_text, font=sub_font, fill=(0, 0, 0))
            draw.text((sx_pos, sy_pos), sub_text, font=sub_font, fill=(255, 80, 80))

        # 6. Xuất ảnh
        if not output_path:
            output_path = "thumbnail.jpg"
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(out_p), "JPEG", quality=95)
        return str(out_p)

    def _create_gradient_background(self) -> Image.Image:
        """Tạo ảnh nền gradient xanh tím huyền ảo khi không có ảnh chụp."""
        img = Image.new("RGB", (self.width, self.height))
        draw = ImageDraw.Draw(img)
        for y in range(self.height):
            ratio = y / self.height
            r = int(10 + 30 * ratio)
            g = int(15 + 20 * ratio)
            b = int(45 + 55 * ratio)
            draw.line([(0, y), (self.width, y)], fill=(r, g, b))
        return img


# Global singleton instance
thumbnail_engine = ThumbnailGenerator()
