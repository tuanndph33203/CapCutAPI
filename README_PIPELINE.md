# CapCut Pipeline

File pipeline chính:

```powershell
C:\Users\PC\Projects\CapCutAPI\capcut_pipeline.py
```

Pipeline này dùng `CapCutAPI` để làm các bước có thể patch bằng lệnh, không cần click UI.

Có danh sách dự án : 
Trong danh sách dự án có thể nhập nhiều video để chạy pipeline lần lượt

## Pipeline cần có

```text
Bước 1 : Chạy ngầm load video vào trong dự án: 
  -> add video vào pipeline
  -> set speed 0.77
  -> set Volumn -15.5Db
Bước 2 : ở init capcut : chọn vào dự án được thiết lập bằng nhận diện tên,
Bước 3 : Chạy nhận diện ảnh : Captions -> Gennerate
Bước 4 : Lấy draff file text tiếng từ capcut dịch sang tiếng việt
Bước 5 : Chạy nhận diện ảnh chọn tất cả text chỉnh cỡ chữ 5, chọn màu vàng
Bước 6 : Chạy nhận diện ảnh : Text to speech -> Icon sao -> giọng bé -> Genarate speech 
Bước 7 : Lấy draff file âm thanh tăng tốc độ lên 1,17
Bước 8 : Chay nhận diện Export
Bước 9 : Chạy nhận diện Cancel -> Icon đóng dự án (X)
```

## Chạy nhanh

Mở PowerShell:

```powershell
cd C:\Users\PC\Projects\CapCutAPI
python capcut_pipeline.py --video "C:\path\to\video.mp4"
```

Lệnh trên sẽ tạo draft test với subtitle mẫu.

## Chạy với SRT Việt

```powershell
cd C:\Users\PC\Projects\CapCutAPI
python capcut_pipeline.py `
  --video "C:\path\to\video.mp4" `
  --srt "C:\path\to\vi.srt" `
  --speed 1.17
```

Kết quả trả về dạng JSON, ví dụ:

```json
{
  "ok": true,
  "draft_id": "dfd_cat_xxxxxxxx",
  "repo_draft": "C:\\Users\\PC\\Projects\\CapCutAPI\\dfd_cat_xxxxxxxx",
  "capcut_draft": "C:\\Users\\PC\\AppData\\Local\\CapCut\\User Data\\Projects\\com.lveditor.draft\\dfd_cat_xxxxxxxx",
  "has_bad_windows_path": false,
  "has_speed": true,
  "has_subtitle_track": true
}
```

## Tham số

```powershell
python capcut_pipeline.py --help
```

Các tham số chính:

```text
--video            Video đầu vào, bắt buộc
--srt              File SRT tiếng Việt, nếu bỏ trống sẽ dùng subtitle test
--speed            Tốc độ video, mặc định 1.17
--clip-seconds     Cắt số giây đầu để test, mặc định 3.0
--width            Width draft, mặc định 1080
--height           Height draft, mặc định 1920
--font             Font subtitle, mặc định HarmonyOS_Sans_SC_Regular
--font-size        Size subtitle, mặc định 8.0
--draft-folder     Thư mục draft CapCut
--no-copy-to-capcut Không copy draft vào thư mục CapCut
```

## Thư mục output

Pipeline tạo draft ở 2 nơi:

```text
C:\Users\PC\Projects\CapCutAPI\dfd_cat_xxxxxxxx
C:\Users\PC\AppData\Local\CapCut\User Data\Projects\com.lveditor.draft\dfd_cat_xxxxxxxx
```

Mở CapCut Home hoặc refresh lại, draft mới sẽ nằm trong danh sách project.

## Các bước vẫn cần UI click

Những bước này chưa làm ngầm được bằng draft JSON ổn định:

```text
Auto Captions tiếng Trung trong CapCut
TTS CapCut chọn giọng bé
Export bằng CapCut
```

Hướng hybrid nên dùng:

```text
1. UI image click: import video / mở draft / Auto Captions tiếng Trung
2. Command: export or read caption draft -> dịch sang SRT Việt
3. Command: capcut_pipeline.py patch SRT Việt + speed 1.17
4. UI image click: tạo TTS giọng bé nếu dùng TTS CapCut
5. UI image click: Export
```

## Lưu ý đã sửa

Đã sửa lỗi Windows path trong:

```text
add_video_track.py
save_draft_impl.py
```

Lỗi cũ tạo path sai dạng:

```text
C:Users\PC\...
```

Path đúng sau khi sửa:

```text
C:\Users\PC\...
```

Nếu không sửa lỗi này, CapCut dễ báo mất media.
