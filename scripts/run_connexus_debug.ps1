# Connexus Debug - Automated Runner for Windows Agent (PowerShell)
# Doc the Puppy 🐶

Write-Host "`n" -NoNewline
Write-Host "================================================================================"
Write-Host "Connexus UI Automation Debug - Automated Mode"
Write-Host "================================================================================"
Write-Host ""

# Check if comtypes is installed
$hasComtypes = $null -ne (python -c "import comtypes" 2>&1)
if (-not $hasComtypes) {
    Write-Host "[ERROR] comtypes not installed!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Installing comtypes..."
    pip install comtypes
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[FAILED] Could not install comtypes" -ForegroundColor Red
        exit 1
    }
    Write-Host "[OK] comtypes installed" -ForegroundColor Green
    Write-Host ""
}

Write-Host "[INFO] Make sure Connexus.exe is running and in foreground!" -ForegroundColor Yellow
Write-Host "[INFO] Starting in 3 seconds..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "================================================================================"
Write-Host "Step 1: Full Tree Analysis"
Write-Host "================================================================================"
Write-Host ""

python scripts/debug_connexus_tree.py --auto --output connexus_tree_debug.json
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "[FAILED] Tree walker failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "================================================================================"
Write-Host "Step 2: List All AutomationIds"
Write-Host "================================================================================"
Write-Host ""

python scripts/debug_connexus_quick.py --list-all-ids --max-results 50
$quickFinderExit = $LASTEXITCODE

Write-Host ""
Write-Host "================================================================================"
Write-Host "SUMMARY"
Write-Host "================================================================================"
Write-Host ""

if ($quickFinderExit -eq 0) {
    Write-Host "[SUCCESS] Found elements with AutomationId!" -ForegroundColor Green
    Write-Host "[INFO] Check connexus_tree_debug.json for full details" -ForegroundColor Cyan
} else {
    Write-Host "[WARNING] No elements with AutomationId found" -ForegroundColor Yellow
    Write-Host "[INFO] Connexus might not use AutomationIds" -ForegroundColor Cyan
    Write-Host "[INFO] Check connexus_tree_debug.json for Name/ClassName properties" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "[OK] Debug complete" -ForegroundColor Green
Write-Host "[FILE] connexus_tree_debug.json" -ForegroundColor Cyan
Write-Host ""

exit 0
