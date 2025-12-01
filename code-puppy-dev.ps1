# code-puppy-dev.ps1
# PowerShell script for testing code-puppy changes during development on Windows
#
# USAGE:
#   .\code-puppy-dev.ps1 --interactive
#   .\code-puppy-dev.ps1 -p "your prompt here"
#
# HOW IT WORKS:
#   1. Sets Walmart's PyPI URL
#   2. Reinstalls code-puppy in development mode
#   3. Runs code-puppy with your arguments

# Capture all arguments
$args_string = $args -join " "

# Set Walmart's internal PyPI URL
$env:UV_INDEX_URL = "https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple"

Write-Host "🐶 Reinstalling code-puppy in development mode..." -ForegroundColor Cyan

# Build and reinstall in development mode (suppress output)
# Temporarily ignore errors from native commands since uv outputs to stderr
$ErrorActionPreference = "SilentlyContinue"
$output = uv pip install --no-deps --force-reinstall -e . 2>&1
$ErrorActionPreference = "Continue"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✅ Reinstall complete!" -ForegroundColor Green
} else {
    Write-Host "⚠️  Reinstall failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "🚀 Running code-puppy with arguments: $args_string" -ForegroundColor Yellow
Write-Host ""

# Run code-puppy with all provided arguments
$env:NO_VERSION_UPDATE = "1"

if ($args_string) {
    uv run code-puppy $args_string
} else {
    uv run code-puppy
}
