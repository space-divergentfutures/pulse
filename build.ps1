# PULSE Windows build script (spec §11).
# Produces a one-dir PyInstaller bundle; optionally wraps it in an Inno Setup installer.
#
# Prerequisites:
#   pip install pyinstaller            (build tool, not in requirements.txt)
#   Inno Setup 6  https://jrsoftware.org/isdl.php  (optional — for the installer)
#
# Usage:
#   .\build.ps1              # builds dist\PULSE\ + installer if ISCC found
#   .\build.ps1 -Version 1.2.0

param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

Write-Host "=== PULSE build $Version ===" -ForegroundColor Cyan

# --- Run tests first ----------------------------------------------------------
Write-Host "Running tests..."
& .\.venv\Scripts\python.exe -m pytest tests/ -q
if ($LASTEXITCODE -ne 0) {
    Write-Host "Tests failed — aborting build." -ForegroundColor Red
    exit 1
}
Write-Host "Tests passed." -ForegroundColor Green

# --- Clean previous build -----------------------------------------------------
foreach ($dir in @("dist", "build")) {
    if (Test-Path $dir) {
        Write-Host "Cleaning $dir\"
        Remove-Item $dir -Recurse -Force
    }
}

# --- PyInstaller one-dir build ------------------------------------------------
Write-Host "Running PyInstaller..."
& .\.venv\Scripts\python.exe -m PyInstaller PULSE.spec
if ($LASTEXITCODE -ne 0) {
    Write-Host "PyInstaller failed." -ForegroundColor Red
    exit 1
}
Write-Host "PyInstaller done — output in dist\PULSE\" -ForegroundColor Green

# --- Inno Setup installer (optional) -----------------------------------------
$isccPaths = @(
    "ISCC",                                          # on PATH
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
)
$iscc = $null
foreach ($p in $isccPaths) {
    $found = Get-Command $p -ErrorAction SilentlyContinue
    if ($found) { $iscc = $found.Source; break }
    if (Test-Path $p) { $iscc = $p; break }
}

if ($iscc) {
    Write-Host "Running Inno Setup ($iscc)..."
    & $iscc "installer\pulse.iss" "/DMyAppVersion=$Version"
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Installer created: installer\PULSE-Setup-$Version.exe" -ForegroundColor Green
    } else {
        Write-Host "Inno Setup failed (exit $LASTEXITCODE)." -ForegroundColor Yellow
    }
} else {
    Write-Host "Inno Setup not found — skipping installer." -ForegroundColor Yellow
    Write-Host "  Install from: https://jrsoftware.org/isdl.php"
    Write-Host "  Then run: ISCC installer\pulse.iss /DMyAppVersion=$Version"
}

Write-Host ""
Write-Host "Build complete." -ForegroundColor Cyan
Write-Host "  App folder : dist\PULSE\"
if ($iscc) {
    Write-Host "  Installer  : installer\PULSE-Setup-$Version.exe"
}
