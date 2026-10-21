# scripts/serve_backend.ps1 -- keep the Jarvis backend (jarvis.server, :8020) up.
#
# Registered as Jarvis_Backend (at logon, hidden via serve_backend.vbs); see
# the project's automation notes. If the
# port already answers, exit 0 quietly (a second instance would just fail to bind);
# otherwise start uvicorn in the project venv and stay attached so Task Scheduler
# restarts it after a crash.
#
# uvicorn logs to stderr. Under $ErrorActionPreference='Stop' a `2>&1` redirect turns
# the first stderr line into a terminating NativeCommandError and the script dies
# with rc 0 (seen 2026-09-23 at first registration). So: Start-Process with file
# redirects, -Wait, and the exit code read back explicitly.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py   = Join-Path $root ".venv\Scripts\python.exe"
$logDir = Join-Path $root "data"
New-Item -ItemType Directory -Force $logDir | Out-Null
$out = Join-Path $logDir "backend.log"
$err = Join-Path $logDir "backend.err.log"

try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 http://127.0.0.1:8020/api/health
    if ($r.StatusCode -eq 200) { Write-Output "jarvis backend already up"; exit 0 }
} catch { }

"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') starting jarvis.server" | Add-Content $out -Encoding utf8
$p = Start-Process -FilePath $py -ArgumentList "-m", "jarvis.server" -WorkingDirectory $root `
    -NoNewWindow -Wait -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
"$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') jarvis.server exited $($p.ExitCode)" | Add-Content $err -Encoding utf8
exit $p.ExitCode
