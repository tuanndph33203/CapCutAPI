$ErrorActionPreference = "SilentlyContinue"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$AppLog = Join-Path $RepoRoot "capcut_gui_app.log"
$MonitorLog = Join-Path $RepoRoot "pipeline_error_monitor.log"
$StateFile = Join-Path $RepoRoot "pipeline_error_monitor.state.json"
$StatusUrl = "http://127.0.0.1:5000/api/status"

function Write-MonitorLog {
    param([string]$Message)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $MonitorLog -Encoding UTF8 -Value "[$ts] $Message"
}

function Load-State {
    if (Test-Path -LiteralPath $StateFile) {
        try {
            return Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
        } catch {}
    }
    [pscustomobject]@{ last_line = 0; last_status = "" }
}

function Save-State {
    param($State)
    $State | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

Write-MonitorLog "Pipeline monitor started. Watching $AppLog"

while ($true) {
    $state = Load-State
    $lastLine = [int]($state.last_line)

    if (Test-Path -LiteralPath $AppLog) {
        $lines = Get-Content -LiteralPath $AppLog -Encoding UTF8
        if ($lines.Count -gt $lastLine) {
            $newLines = $lines[$lastLine..($lines.Count - 1)]
            foreach ($line in $newLines) {
                if ($line -match "ERROR|CRITICAL|Traceback|template not found|wait timeout|Lỗi khi tự động hóa|thất bại") {
                    Write-MonitorLog "ALERT log: $line"
                }
            }
            $state.last_line = $lines.Count
        }
    }

    try {
        $status = Invoke-RestMethod -Uri $StatusUrl -TimeoutSec 3
        $summary = "processing=$($status.is_processing); paused=$($status.is_paused); index=$($status.current_index); queue=$(@($status.queue).Count)"
        if ($summary -ne $state.last_status) {
            Write-MonitorLog "STATUS $summary"
            $state.last_status = $summary
        }
    } catch {
        if ($state.last_status -ne "server=down") {
            Write-MonitorLog "STATUS server=down"
            $state.last_status = "server=down"
        }
    }

    Save-State $state
    Start-Sleep -Seconds 5
}
