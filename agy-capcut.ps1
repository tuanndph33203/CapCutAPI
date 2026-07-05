param(
    [Parameter(Mandatory = $true)]
    [string]$DraftPath,

    [string]$SkillPath = "C:\Users\nguye\.gemini\config\skills\capcut_draft_tracking\SKILL.md",
    [string]$Model = "Gemini 3.5 Flash (Medium)",
    [int]$TimeoutSeconds = 600,
    [string]$AgyExe = "$env:LOCALAPPDATA\agy\bin\agy.exe",
    [string]$ProgressPath = "",
    [string]$Task = "Dịch toàn bộ subtitle tiếng Trung sang tiếng Việt tự nhiên, đúng ngữ cảnh và patch trực tiếp vào draft."
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $AgyExe)) {
    throw "Không tìm thấy agy.exe tại: $AgyExe"
}

if (-not (Test-Path -LiteralPath $DraftPath)) {
    throw "Không tìm thấy draft path: $DraftPath"
}

if (-not $ProgressPath) {
    $ProgressPath = Join-Path $DraftPath "translation_progress.json"
}

# Extract chỉ phần subtitle cần dịch ra file nhỏ để tiết kiệm token
$ExtractScript = "C:\Users\nguye\.gemini\antigravity-ide\scratch\extract_subtitles_to_translate.js"
$ExtractedPath = Join-Path $DraftPath "subtitles_to_translate.json"

Write-Host "[agy-capcut] Extracting subtitles..." -ForegroundColor Cyan
node $ExtractScript $DraftPath

# Đọc nội dung file subtitle extract để nhúng trực tiếp vào prompt (tiết kiệm token)
$SubtitleContent = ""
if (Test-Path -LiteralPath $ExtractedPath) {
    $SubtitleContent = Get-Content -LiteralPath $ExtractedPath -Raw -Encoding UTF8
    Write-Host "[agy-capcut] Loaded extracted subtitles ($($SubtitleContent.Length) chars)" -ForegroundColor Green
}
else {
    Write-Host "[agy-capcut] Extract failed, AI will read draft_content.json directly" -ForegroundColor Yellow
}

$SubtitleSection = if ($SubtitleContent) {
    @"

--- SUBTITLE DATA (đã extract sẵn, chỉ chứa các dòng cần dịch) ---
$SubtitleContent
--- END SUBTITLE DATA ---
"@
} else {
    "`nKhông có file extract sẵn. Hãy tự đọc draft_content.json trong thư mục draft để tìm subtitle tiếng Trung."
}

$Prompt = @"
Đọc và tuân thủ skill tại:
$SkillPath

Thư mục draft CapCut (dùng để patch file):
$DraftPath
$SubtitleSection

Nhiệm vụ:
1. $Task
2. Dịch tất cả subtitle tiếng Trung → tiếng Việt tự nhiên, đúng ngữ cảnh.
3. Patch kết quả dịch trực tiếp vào draft_content.json trong thư mục draft.
4. Đồng bộ text trong materials.texts và subtitle_cache_info nếu có.
5. Giữ nguyên id, timing, segment, material structure, style/position.
6. Không sửa video/audio timing. Không đổi tên project. Không export.
7. Sau khi patch xong, tạo file translated_vietnamese.srt trong thư mục draft nếu có thể.
8. Kiểm tra lại; nếu còn subtitle tiếng Trung thì tiếp tục patch cho sạch.
9. Trong lúc làm, cập nhật tiến độ vào file JSON này:
   $ProgressPath
   Format:
   {"stage":"reading|translating|patching|verifying|done","message":"...", "percent":0-100}
   Hãy ghi file này sau mỗi bước lớn hoặc sau mỗi khoảng 20 dòng subtitle.

Chỉ khi hoàn tất, trả lời JSON ngắn gọn:
{"success": true, "patched": <số dòng>, "files": <số file>}
Nếu lỗi:
{"success": false, "error": "..."}
"@

Write-Host "[agy-capcut] Calling agy with model: $Model" -ForegroundColor Cyan
& $AgyExe `
    --dangerously-skip-permissions `
    --add-dir $DraftPath `
    --model $Model `
    --print $Prompt `
    --print-timeout "$($TimeoutSeconds)s"
