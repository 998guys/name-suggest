[CmdletBinding()]
param([switch]$SkipModelDownload)

$ErrorActionPreference = 'Stop'
$sourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appDir = Join-Path $env:LOCALAPPDATA 'VoiceTyper'
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'Python 3.10–3.12 is required. Install it from python.org and enable Add python.exe to PATH.' }

Write-Host '[1/5] Checking Python...'
& $python.Source -c "import sys; assert sys.maxsize > 2**32, '64-bit Python is required'; assert (3,10) <= sys.version_info[:2] <= (3,12), 'Python 3.10-3.12 is required'"
if ($LASTEXITCODE -ne 0) { throw 'The installed Python version is not compatible.' }

Write-Host '[2/5] Copying Voice Typer...'
Get-CimInstance Win32_Process -Filter "Name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -and $_.CommandLine.Contains('VoiceTyper\voice_typer.py') } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
if (Test-Path $appDir) { Remove-Item $appDir -Recurse -Force }
New-Item -ItemType Directory -Path $appDir | Out-Null
Copy-Item (Join-Path $sourceDir '*') $appDir -Recurse -Force

Write-Host '[3/5] Creating an isolated Python environment...'
& $python.Source -m venv (Join-Path $appDir '.venv')
if ($LASTEXITCODE -ne 0) { throw 'Could not create the app environment.' }
$appPython = Join-Path $appDir '.venv\Scripts\python.exe'
$appPythonW = Join-Path $appDir '.venv\Scripts\pythonw.exe'

Write-Host '[4/5] Installing speech and typing components...'
& $appPython -m pip install --disable-pip-version-check --upgrade pip
& $appPython -m pip install --disable-pip-version-check -r (Join-Path $appDir 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your internet connection and try again.' }

if (-not $SkipModelDownload) {
    Write-Host '[5/5] Downloading the offline English speech model (one time only)...'
    & $appPython (Join-Path $appDir 'voice_typer.py') --download-model
    if ($LASTEXITCODE -ne 0) { throw 'The speech model could not be downloaded. Check your connection and run the installer again.' }
} else {
    Write-Host '[5/5] Skipping model download; the app will download it on first launch.'
}

$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath('Desktop')
$startMenu = [Environment]::GetFolderPath('Programs')
foreach ($folder in @($desktop, $startMenu)) {
    $shortcut = $shell.CreateShortcut((Join-Path $folder 'Voice Typer.lnk'))
    $shortcut.TargetPath = $appPythonW
    $shortcut.Arguments = '"' + (Join-Path $appDir 'voice_typer.py') + '"'
    $shortcut.WorkingDirectory = $appDir
    $shortcut.IconLocation = Join-Path $appDir 'assets\voice_typer.ico'
    $shortcut.Description = 'Private offline voice typing'
    $shortcut.Save()
}

Write-Host ''
Write-Host 'Voice Typer installed successfully.' -ForegroundColor Green
Write-Host 'Open Voice Typer from the desktop or Start Menu.'
Write-Host 'Start/stop: Ctrl+Alt+Shift+L    Quit: Ctrl+Alt+Shift+Q'
