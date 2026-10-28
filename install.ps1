# Code GPT CLI installer for Windows.  Usage (PowerShell):  irm https://codegpt.it.com/install.ps1 | iex
$ErrorActionPreference = 'Stop'
$AppUrl = 'https://chat.codegpt.it.com'
$Dir = Join-Path $env:USERPROFILE '.codegpt'
$Bin = Join-Path $Dir 'bin'
Write-Host 'Installing the Code GPT CLI...'
$py = $null
foreach ($c in @('py', 'python', 'python3')) {
  $cmd = Get-Command $c -ErrorAction SilentlyContinue
  if ($cmd -and $cmd.Source -notlike '*WindowsApps*') {
    & $c -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $py = $cmd.Source; break }
  }
}
if (-not $py) {
  Write-Host 'The Code GPT CLI needs Python 3.8 or newer. Install it with:' -ForegroundColor Yellow
  Write-Host '  winget install Python.Python.3.12'
  Write-Host 'or from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then run this installer again.'
  return
}
New-Item -ItemType Directory -Force -Path $Bin | Out-Null
Invoke-WebRequest -UseBasicParsing -Uri "$AppUrl/static/downloads/codegpt-cli/codegpt.py" -OutFile (Join-Path $Dir 'codegpt.py')
Set-Content -Path (Join-Path $Bin 'codegpt.cmd') -Encoding ASCII -Value "@echo off`r`n`"$py`" `"$Dir\codegpt.py`" %*"
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if (-not $userPath) { $userPath = '' }
if (-not ($userPath -split ';' | Where-Object { $_ -eq $Bin })) {
  [Environment]::SetEnvironmentVariable('Path', ($userPath.TrimEnd(';') + ';' + $Bin), 'User')
  Write-Host "Added $Bin to your PATH. Open a new terminal window."
}
$env:Path = $env:Path + ';' + $Bin
Write-Host ''
Write-Host 'Done. Start with:   codegpt login' -ForegroundColor Green
