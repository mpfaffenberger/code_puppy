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
$uvCmd = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCmd) {
    Write-Host "uv not found, installing via Walmart Artifactory pypi mirror..."
    # McAfee Web Gateway blocks direct downloads from astral.sh on the vs2022
    # CI agent, so we install uv via pip from the same Artifactory mirror the
    # Linux flows already use. No proxy / Invoke-WebRequest gymnastics needed.
    & pip install `
        --index-url "https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple" `
        --quiet `
        uv
    if ($LASTEXITCODE -ne 0) { throw "pip install uv failed (exit $LASTEXITCODE)" }
    # pip on Windows installs uv.exe to either:
    #   - <python-prefix>\Scripts\uv.exe   (system / venv python)
    #   - %APPDATA%\Python\Python3X\Scripts\uv.exe   (--user installs)
    # Both should be on PATH already if pip itself was installed normally; if not,
    # prepend the most common locations so the rest of the script can find uv.
    $userScripts = Join-Path $env:APPDATA "Python\Python313\Scripts"
    if (Test-Path $userScripts) { $env:PATH = "$userScripts;$env:PATH" }
    # Also try whatever python -m site --user-base reports
    try {
        $userBase = & python -c "import site; print(site.USER_BASE)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $userBase) {
            $candidate = Join-Path $userBase "Scripts"
            if (Test-Path $candidate) { $env:PATH = "$candidate;$env:PATH" }
        }
    } catch {}
} else {
    Write-Host "uv already on PATH at $($uvCmd.Source)"
}

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
