param([switch]$RemoveData)

$ErrorActionPreference = 'Stop'
$appDir = Join-Path $env:LOCALAPPDATA 'VoiceTyper'
$dataDir = Join-Path $env:APPDATA 'VoiceTyper'
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = [Environment]::GetFolderPath('Programs')

Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains('VoiceTyper\voice_typer.py') } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'VoiceTyper' -ErrorAction SilentlyContinue
Remove-Item (Join-Path $desktop 'Voice Typer.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $startMenu 'Voice Typer.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item $appDir -Recurse -Force -ErrorAction SilentlyContinue
if ($RemoveData) { Remove-Item $dataDir -Recurse -Force -ErrorAction SilentlyContinue }
Write-Host 'Voice Typer was uninstalled.'
if (-not $RemoveData) { Write-Host "Your learned phrases and speech model were preserved in $dataDir" }
