# ============================================================================
# build_portable_venv.ps1 - Build a relocatable portable venv on Windows
# ============================================================================
# Creates a `uv venv --relocatable` venv, installs the freshly-built
# code-puppy wheel from dist/, and zips the venv into a distributable archive.
# ============================================================================

param(
    [Parameter(Mandatory)]
    [string]$Version,

    [string]$VenvPath = ".venv-portable",

    [string]$ZipOutPath = "code-puppy-venv-windows.zip"
)

$ErrorActionPreference = "Stop"

Write-Host "Creating portable venv with uv (--relocatable)..."
uv venv --relocatable --python 3.13 $VenvPath
if ($LASTEXITCODE -ne 0) {
    Write-Error "uv venv failed"
    exit 1
}

$wheel = Get-ChildItem dist\*.whl | Select-Object -First 1
if (-not $wheel) {
    Write-Error "No wheel found in dist/"
    exit 1
}

Write-Host "Installing $($wheel.Name) into portable venv..."
uv pip install --python "$VenvPath\Scripts\python.exe" $wheel.FullName
if ($LASTEXITCODE -ne 0) {
    Write-Error "uv pip install failed"
    exit 1
}

Write-Host "Zipping venv to $ZipOutPath..."
if (Test-Path $ZipOutPath) { Remove-Item $ZipOutPath -Force }
Compress-Archive -Path "$VenvPath\*" -DestinationPath $ZipOutPath -CompressionLevel Optimal

$sizeMB = [math]::Round((Get-Item $ZipOutPath).Length / 1MB, 2)
Write-Host "Built: $ZipOutPath ($sizeMB MB) for code-puppy v$Version"
