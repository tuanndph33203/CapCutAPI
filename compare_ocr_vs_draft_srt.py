import os, re, sys
sys.stdout.reconfigure(encoding='utf-8')

ocr_path = r"C:\Users\nguye\Projects\CapCutAPI\00000000000\ocr_zh.srt"
draft_srt_path = r"C:\Users\nguye\Projects\CapCutAPI\capcut_draft_subtitles.srt"

def parse_srt(p):
    content = open(p, encoding='utf-8').read()
    blocks = re.split(r'\n\s*\n', content.strip())
    res = []
    for b in blocks:
        lines = [l.strip() for l in b.split('\n') if l.strip()]
        if len(lines) >= 3:
            idx = lines[0]
            ts = lines[1]
            m = re.match(r'(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)', ts)
            if m:
                h1,m1,s1,ms1,h2,m2,s2,ms2 = map(int, m.groups())
                st = h1*3600 + m1*60 + s1 + ms1/1000.0
                et = h2*3600 + m2*60 + s2 + ms2/1000.0
                txt = ' '.join(lines[2:])
                res.append({'idx': idx, 'start': st, 'end': et, 'text': txt})
    return res

ocr_subs = parse_srt(ocr_path)
draft_subs = parse_srt(draft_srt_path)

print("=======================================================================================================")
print(f"=== BÁO CÁO SO SÁNH TIMESTAMP CHI TIẾT (RAW OCR ocr_zh.srt VS DRAFT CAPCUT capcut_draft_subtitles.srt) ===")
print("=======================================================================================================")
print(f"Tổng số câu OCR Gốc: {len(ocr_subs)} | Tổng số câu Draft Mới: {len(draft_subs)}")
print("-------------------------------------------------------------------------------------------------------")
print(f"{'Câu':<5} | {'Thời gian Gốc (ocr_zh.srt)':<28} | {'Thời gian Mới (Draft)':<28} | {'Tỷ lệ (Mới/Gốc)':<12} | {'Độ Lệch (s)':<10}")
print("-------------------------------------------------------------------------------------------------------")

for i in range(min(len(ocr_subs), len(draft_subs))):
    o = ocr_subs[i]
    d = draft_subs[i]
    ratio = d['start'] / o['start'] if o['start'] > 0 else 1.0
    diff = d['start'] - o['start']
    o_str = f"{int(o['start']//60):02d}:{o['start']%60:05.2f}s -> {int(o['end']//60):02d}:{o['end']%60:05.2f}s"
    d_str = f"{int(d['start']//60):02d}:{d['start']%60:05.2f}s -> {int(d['end']//60):02d}:{d['end']%60:05.2f}s"
    
    # Print milestone rows
    if i in (0, 1, 2, 3, 4, 8, 13, 22, 30, 40, 45, 50, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63):
        print(f"#{i+1:<4} | {o_str:<28} | {d_str:<28} | {ratio:6.4f}x      | {diff:+6.2f}s")

print("=======================================================================================================")
print(f"📌 Mốc cuối cùng OCR Gốc (ocr_zh.srt):  {int(ocr_subs[-1]['end']//60):02d}:{ocr_subs[-1]['end']%60:05.2f}s ({ocr_subs[-1]['end']:.2f}s)")
print(f"📌 Mốc cuối cùng Draft Mới (CapCut):     {int(draft_subs[-1]['end']//60):02d}:{draft_subs[-1]['end']%60:05.2f}s ({draft_subs[-1]['end']:.2f}s)")
print(f"📊 Độ dãn tổng thể: {draft_subs[-1]['end'] / ocr_subs[-1]['end']:.4f}x (+{draft_subs[-1]['end'] - ocr_subs[-1]['end']:.2f}s)")
print("=======================================================================================================")
