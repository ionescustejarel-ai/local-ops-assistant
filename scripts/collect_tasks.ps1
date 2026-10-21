# scripts/collect_tasks.ps1 -- dump the watched scheduled tasks as JSON (state, last/next run, result, trigger interval).
# Read-only. Used by jarvis/collectors/tasks.py; nulls are preserved so the parser can handle never-run tasks.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$pattern = if ($args.Count -gt 0) { $args[0] } else { '^(Ops|Jarvis)' }
$rows = Get-ScheduledTask | Where-Object { $_.TaskName -match $pattern } | ForEach-Object {
    $i = $_ | Get-ScheduledTaskInfo
    $t = $_.Triggers | Select-Object -First 1
    $fmt = { param($d) if ($null -eq $d -or $d.Year -lt 2000) { $null } else { $d.ToString('o') } }
    [pscustomobject]@{
        TaskName          = $_.TaskName
        State             = [string]$_.State
        LastRunTime       = & $fmt $i.LastRunTime
        LastTaskResult    = $i.LastTaskResult
        NextRunTime       = & $fmt $i.NextRunTime
        NumberOfMissedRuns = $i.NumberOfMissedRuns
        TriggerClass      = if ($t) { $t.CimClass.CimClassName } else { $null }
        RepetitionInterval = if ($t -and $t.Repetition) { $t.Repetition.Interval } else { $null }
        StartBoundary     = if ($t) { $t.StartBoundary } else { $null }
    }
}
ConvertTo-Json -InputObject @($rows) -Depth 3
