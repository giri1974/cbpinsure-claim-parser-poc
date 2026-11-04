<#
  Installs Tesseract OCR (UB Mannheim Windows build) without needing admin rights,
  into  %LOCALAPPDATA%\Programs\Tesseract-OCR , then verifies it and writes TESSERACT_CMD to .env.

  Run from the project folder:
      powershell -ExecutionPolicy Bypass -File .\scripts\install_tesseract.ps1
  Optional:  -Version 5.4.0.20240606   -InstallDir "D:\Tools\Tesseract-OCR"
#>
param(
    [string]$Version    = "5.4.0.20240606",
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA "Programs\Tesseract-OCR")
)
$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = "SilentlyContinue"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $InstallDir "tesseract.exe"

function Test-Tesseract($path) {
    if (Test-Path $path) { & $path --version 2>&1 | Select-Object -First 1 } else { $null }
}

# 1. Already installed?
$existing = Get-Command tesseract -ErrorAction SilentlyContinue
if ($existing) { $exe = $existing.Source }
$ver = Test-Tesseract $exe
if ($ver) { Write-Host "Tesseract already installed: $ver ($exe)" -ForegroundColor Green }
else {
    # 2. Download the installer
    $name = "tesseract-ocr-w64-setup-$Version.exe"
    $urls = @(
        "https://github.com/UB-Mannheim/tesseract/releases/download/v$Version/$name",
        "https://digi.bib.uni-mannheim.de/tesseract/$name"
    )
    $installer = Join-Path $env:TEMP $name
    $ok = $false
    foreach ($u in $urls) {
        try {
            Write-Host "Downloading $u ..."
            Invoke-WebRequest -Uri $u -OutFile $installer -UseBasicParsing
            if ((Get-Item $installer).Length -gt 20MB) { $ok = $true; break }
        } catch { Write-Host "  failed: $($_.Exception.Message)" -ForegroundColor Yellow }
    }
    if (-not $ok) { throw "Could not download the Tesseract installer. Download it manually from https://github.com/UB-Mannheim/tesseract/wiki" }

    # 3. Silent per-user install (/D must be the last argument and unquoted)
    Write-Host "Installing to $InstallDir ..."
    $p = Start-Process -FilePath $installer -ArgumentList "/S", "/D=$InstallDir" -Wait -PassThru
    if ($p.ExitCode -ne 0) { throw "Installer exited with code $($p.ExitCode)" }
    $exe = Join-Path $InstallDir "tesseract.exe"
    $ver = Test-Tesseract $exe
    if (-not $ver) { throw "tesseract.exe not found after install at $exe" }
    Write-Host "Installed: $ver" -ForegroundColor Green
    Remove-Item $installer -ErrorAction SilentlyContinue
}

# 4. Make sure the English model exists
$td = Join-Path (Split-Path $exe -Parent) "tessdata"
if (-not (Test-Path (Join-Path $td "eng.traineddata"))) {
    Write-Host "Downloading eng.traineddata ..."
    Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_best/raw/main/eng.traineddata" -OutFile (Join-Path $td "eng.traineddata")
}

# 5. Tell the project where Tesseract is (kept in .env, which is git-ignored)
$envFile = Join-Path $ProjectRoot ".env"
$line = "TESSERACT_CMD=$exe"
$content = if (Test-Path $envFile) { Get-Content $envFile | Where-Object { $_ -notmatch '^TESSERACT_CMD=' } } else { @() }
@($content) + $line | Set-Content $envFile -Encoding UTF8
Write-Host "Wrote $line to .env" -ForegroundColor Green
Write-Host "Done. Restart the Streamlit server so it picks up the change." -ForegroundColor Cyan
