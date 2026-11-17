# 注册定时任务：以当前用户身份、交互式运行，因此 Outlook 必须保持登录并处于运行状态。
param(
    [string]$TaskName = "OutlookDigest",
    [int]$IntervalMinutes = 30,
    [string]$PythonExe = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not $PythonExe) {
    $PythonExe = Join-Path $root ".venv\Scripts\pythonw.exe"
}
if (-not (Test-Path $PythonExe)) {
    throw "找不到 $PythonExe，请先在项目根目录创建虚拟环境并安装依赖"
}

$action = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "-m outlook_digest run" `
    -WorkingDirectory $root

$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "定时读取 Outlook，翻译/分析/总结并归档到 Markdown" `
    -Force | Out-Null

Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
Write-Host "已注册：每 $IntervalMinutes 分钟运行一次。手动试跑：Start-ScheduledTask -TaskName $TaskName"
