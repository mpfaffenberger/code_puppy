# ============================================================================
# build_and_upload_windows_venv.ps1
# ============================================================================
# Orchestrates the Windows portable-venv build + GCS upload from Looper Pro.
# Called from the `build_and_upload_windows_venv` flow in .looper.yml.
#
# Why this exists as a .ps1 instead of an inline `- shell: |` CMD block:
# CMD performs early %PATH% expansion inside `if (...)` parens. The vs2022
# agent's PATH contains `C:\Program Files\Git\cmd` (spaces + special chars)
# which collides with multi-line PowerShell calls inside the parens, blowing
# up with `\Git\cmd was unexpected at this time`. PowerShell has no such
# problem, and this also matches how puppy-launcher does heavier Windows
# lifting via .ps1 helpers.
#
# Required env: GCS_SA_KEY_B64 (base64-encoded service account JSON)
# ============================================================================

$ErrorActionPreference = "Stop"

Write-Host "=== build_and_upload_windows_venv.ps1 ==="

# --- 1. Ensure uv + Python are available ---
# ---------------------------------------------------------------
# The vs2022 agent has neither Python nor uv on PATH, AND McAfee
# Web Gateway blocks both github.com (uv's default Python download)
# and astral.sh (the uv installer). So we pull both binaries from
# puppy-backend, which proxies them out of GCS / Artifactory:
#
#   GET https://puppy-backend.stg.walmart.com/uv/download/windows
#   GET https://puppy-backend.stg.walmart.com/python/download/windows
#
# Using stage during the Windows-CI iteration. Same GCS bucket as prod
# (gs://puppy-pages), same artifacts, faster deploy cadence. Switch to
# puppy-backend.walmart.com once Windows pipeline is green.
#
# After install we set UV_PYTHON_PREFERENCE=only-system so uv uses
# the python.exe we just unpacked instead of trying to download its
# own (which would hit github.com and fail).
# ---------------------------------------------------------------

$puppyBackend = "https://puppy-backend.stg.walmart.com"

# --- 1a. Download + install uv ---
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not on PATH - downloading from puppy-backend..."
    $uvZipUrl = "$puppyBackend/uv/download/windows"
    $uvZip = Join-Path $env:TEMP "uv.zip"
    $uvDir = Join-Path $env:USERPROFILE ".uv-bin"
    Invoke-WebRequest -Uri $uvZipUrl -OutFile $uvZip -UseBasicParsing -TimeoutSec 120
    if (Test-Path $uvDir) { Remove-Item -Recurse -Force $uvDir }
    Expand-Archive -Path $uvZip -DestinationPath $uvDir -Force
    Remove-Item $uvZip -Force
    $uvExe = Get-ChildItem -Path $uvDir -Filter "uv.exe" -Recurse | Select-Object -First 1
    if (-not $uvExe) { throw "uv.exe not found after extraction from $uvZipUrl" }
    $env:PATH = "$($uvExe.DirectoryName);$env:PATH"
    Write-Host "Installed uv $(& uv --version) at $($uvExe.FullName)"
} else {
    Write-Host "uv already on PATH at $((Get-Command uv).Source) - version: $(& uv --version)"
}

# --- 1b. Download + install Python ---
$pythonRoot = Join-Path $env:USERPROFILE ".python-bin"
$pythonExe = Get-ChildItem -Path $pythonRoot -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $pythonExe) {
    Write-Host "Python not present in $pythonRoot - downloading from puppy-backend..."
    $pyTar = Join-Path $env:TEMP "python.tar.gz"
    $pyUrl = "$puppyBackend/python/download/windows"
    Invoke-WebRequest -Uri $pyUrl -OutFile $pyTar -UseBasicParsing -TimeoutSec 300
    if (Test-Path $pythonRoot) { Remove-Item -Recurse -Force $pythonRoot }
    New-Item -ItemType Directory -Path $pythonRoot | Out-Null
    # tar.exe ships with Win10+ / Server 2019+; same trick puppy-launcher uses.
    & tar.exe -xzf $pyTar -C $pythonRoot
    if ($LASTEXITCODE -ne 0) { throw "tar -xzf failed (exit $LASTEXITCODE) for $pyTar" }
    Remove-Item $pyTar -Force
    $pythonExe = Get-ChildItem -Path $pythonRoot -Filter "python.exe" -Recurse | Select-Object -First 1
    if (-not $pythonExe) { throw "python.exe not found after extracting $pyUrl into $pythonRoot" }
}
$env:PATH = "$($pythonExe.DirectoryName);$env:PATH"
Write-Host "Using Python at $($pythonExe.FullName)"
& python --version
if ($LASTEXITCODE -ne 0) { throw "python --version failed" }

# --- 1c. Tell uv to ONLY use the system Python we just installed ---
# UV_PYTHON pins the version; UV_PYTHON_PREFERENCE=only-system stops uv
# from trying to download its own (which would hit github.com and fail).
$env:UV_PYTHON = "3.13"
$env:UV_PYTHON_PREFERENCE = "only-system"

# --- 1d. Pin uv's package index to Walmart Artifactory ---
# Default PyPI (pypi.org) is blocked by McAfee on the vs2022 agents.
# Mirror Linux phase config: --native-tls + --index-url => env vars so
# every uv invocation in the child build_portable_venv.ps1 inherits them.
$env:UV_INDEX_URL = "https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple"
$env:UV_NATIVE_TLS = "1"

# Verify uv works
& uv --version
if ($LASTEXITCODE -ne 0) { throw "uv --version failed" }

# --- 2. Determine the version ---
# Build the wheel first so we can ask the installed package for its version.
Write-Host "Building wheel..."
& uv --native-tls build
if ($LASTEXITCODE -ne 0) { throw "uv build failed" }

# Read version from pyproject.toml (more reliable than importing on a fresh checkout)
$pyprojectContent = Get-Content "pyproject.toml" -Raw
if ($pyprojectContent -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
    throw "Could not parse version from pyproject.toml"
}
$Version = $Matches[1]
Write-Host "Resolved version: $Version"

# --- 3. Build the portable venv ---
Write-Host "Building portable venv (version $Version)..."
& powershell -ExecutionPolicy Bypass -File scripts\build_portable_venv.ps1 -Version $Version
if ($LASTEXITCODE -ne 0) { throw "build_portable_venv.ps1 failed (exit $LASTEXITCODE)" }

# --- 4. Upload to GCS ---
$saKey = $env:GCS_SA_KEY_B64
if (-not $saKey) { throw "GCS_SA_KEY_B64 env var is not set" }

Write-Host "Uploading code-puppy-venv-windows.zip to GCS..."
& powershell -ExecutionPolicy Bypass -File scripts\upload_venv_to_gcs.ps1 `
    -ZipPath "code-puppy-venv-windows.zip" `
    -Version $Version `
    -SaKeyBase64 $saKey `
    -Platform "windows"
if ($LASTEXITCODE -ne 0) { throw "upload_venv_to_gcs.ps1 failed (exit $LASTEXITCODE)" }

Write-Host "=== Windows venv build + upload complete (v$Version) ==="
