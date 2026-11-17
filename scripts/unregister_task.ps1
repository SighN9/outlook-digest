param([string]$TaskName = "OutlookDigest")

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Write-Host "任务 $TaskName 不存在"
    return
}
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
Write-Host "已删除计划任务 $TaskName"
