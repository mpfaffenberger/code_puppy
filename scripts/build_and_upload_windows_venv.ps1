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

# --- 1. Ensure uv is installed ---
# ---------------------------------------------------------------
# Ensure uv is available. The vs2022 agent has neither Python nor
# uv on PATH, so we download uv.exe directly from Walmart's
# Artifactory mirror of astral-sh's GitHub releases. uv will then
# bootstrap its own Python interpreter on demand via `--python 3.13`.
#
# This is the same approach puppy-launcher uses in
# scripts/build_crucible.ps1.
# ---------------------------------------------------------------
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not on PATH - downloading from Walmart Artifactory GitHub mirror..."
    $uvZipUrl = "https://generic.ci.artifacts.walmart.com/artifactory/github-releases-generic-release-remote/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
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

# Tell uv which Python to use for every subsequent invocation. The agent has
# no system Python, so uv will download 3.13 into its managed cache on first
# use (uv venv / uv build / uv pip install).
$env:UV_PYTHON = "3.13"

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
