# scripts/register_tasks.ps1 -- register the two logon tasks (idempotent, -Force).
#   Jarvis_Backend : serve_backend.vbs  (python backend :8020, restarts on crash)
#   Jarvis_App     : start_app.vbs      (Electron window + tray)
# Run once from an elevated or normal shell.
$ErrorActionPreference = "Stop"
$scripts = $PSScriptRoot
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 30)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger.Delay = "PT20S"

Register-ScheduledTask -TaskName "Jarvis_Backend" -Force -Trigger $trigger -Settings $settings `
    -Action (New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$scripts\serve_backend.vbs`"") `
    -Description "Jarvis backend (FastAPI :8020): collectors, whisper STT, edge-tts, claude -p brain" | Out-Null

$trigger2 = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$trigger2.Delay = "PT40S"
Register-ScheduledTask -TaskName "Jarvis_App" -Force -Trigger $trigger2 -Settings $settings `
    -Action (New-ScheduledTaskAction -Execute "wscript.exe" -Argument "`"$scripts\start_app.vbs`"") `
    -Description "Jarvis desktop window (Electron) with tray + Ctrl+Alt+J push-to-talk" | Out-Null

Get-ScheduledTask -TaskName "Jarvis_*" | Select-Object TaskName, State | Format-Table -AutoSize
