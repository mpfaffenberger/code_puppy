# uninstall-gcloud.ps1
# PowerShell script to completely uninstall Google Cloud SDK on Windows

Write-Host "🗑️  Uninstalling Google Cloud SDK..." -ForegroundColor Yellow

# Remove gcloud installation directory
$installPath = Join-Path $env:LOCALAPPDATA "Google\CloudSDK"
if (Test-Path $installPath) {
    Write-Host "Removing installation directory: $installPath"
    Remove-Item $installPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "✓ Installation directory removed" -ForegroundColor Green
} else {
    Write-Host "Installation directory not found: $installPath" -ForegroundColor Yellow
}

# Remove from User PATH (permanent)
Write-Host "Cleaning User PATH..."
$currentPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$pathEntries = $currentPath -split ';'
$filteredPath = $pathEntries | Where-Object { 
    $_ -notlike '*CloudSDK*' -and 
    $_ -notlike '*google-cloud-sdk*' -and
    $_ -ne ''
}
$newPath = $filteredPath -join ';'

if ($currentPath -ne $newPath) {
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
    Write-Host "✓ User PATH cleaned" -ForegroundColor Green
} else {
    Write-Host "User PATH already clean" -ForegroundColor Yellow
}

# Remove from current session PATH
Write-Host "Cleaning session PATH..."
$sessionPathEntries = $env:PATH -split ';'
$filteredSessionPath = $sessionPathEntries | Where-Object { 
    $_ -notlike '*CloudSDK*' -and 
    $_ -notlike '*google-cloud-sdk*' -and
    $_ -ne ''
}
$env:PATH = $filteredSessionPath -join ';'
Write-Host "✓ Session PATH cleaned" -ForegroundColor Green

# Verify removal
Write-Host ""
$gcloudExists = Get-Command gcloud -ErrorAction SilentlyContinue
if ($gcloudExists) {
    Write-Host "⚠️  Warning: gcloud command still found in PATH" -ForegroundColor Yellow
    Write-Host "Location: $($gcloudExists.Source)" -ForegroundColor Yellow
    Write-Host "You may need to close and reopen your terminal." -ForegroundColor Yellow
} else {
    Write-Host "✅ Google Cloud SDK successfully uninstalled!" -ForegroundColor Green
    Write-Host "You can now reinstall with: /bigquery_auth" -ForegroundColor Cyan
}
