# Code Puppy Windows Setup Script
# Enables long path support required for building certain dependencies like winsdk

#Requires -RunAsAdministrator

Write-Host "🐶 Code Puppy Windows Setup" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check if running as administrator
$currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "❌ This script requires administrator privileges." -ForegroundColor Red
    Write-Host "Please run PowerShell as Administrator and try again." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Right-click PowerShell and select 'Run as Administrator'" -ForegroundColor Yellow
    exit 1
}

Write-Host "✅ Running with administrator privileges" -ForegroundColor Green
Write-Host ""

# Function to check if long paths are enabled
function Test-LongPathsEnabled {
    try {
        $regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem"
        $regName = "LongPathsEnabled"
        $value = Get-ItemProperty -Path $regPath -Name $regName -ErrorAction SilentlyContinue
        return ($value.$regName -eq 1)
    } catch {
        return $false
    }
}

# Check current status
Write-Host "📋 Checking current long path configuration..." -ForegroundColor Cyan
$isEnabled = Test-LongPathsEnabled

if ($isEnabled) {
    Write-Host "✅ Long paths are already enabled!" -ForegroundColor Green
    Write-Host ""
    Write-Host "You're all set! You can now install code-puppy:" -ForegroundColor Green
    Write-Host "  uvx code-puppy -i" -ForegroundColor White
    Write-Host ""
    exit 0
}

Write-Host "⚠️  Long paths are currently disabled" -ForegroundColor Yellow
Write-Host ""
Write-Host "This is required for building certain Windows dependencies (like winsdk)" -ForegroundColor White
Write-Host "that have deep directory structures during compilation." -ForegroundColor White
Write-Host ""

# Ask for confirmation
$confirmation = Read-Host "Do you want to enable long path support? (Y/N)"
if ($confirmation -ne 'Y' -and $confirmation -ne 'y') {
    Write-Host "❌ Setup cancelled by user" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "🔧 Enabling long path support..." -ForegroundColor Cyan

try {
    # Enable long paths in FileSystem
    $regPath = "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem"
    New-ItemProperty -Path $regPath -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force | Out-Null
    Write-Host "✅ Enabled LongPathsEnabled in FileSystem" -ForegroundColor Green

    # Also enable for Python if the registry path exists
    $pythonRegPath = "HKLM:\SOFTWARE\Python\PythonCore"
    if (Test-Path $pythonRegPath) {
        New-ItemProperty -Path $pythonRegPath -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force -ErrorAction SilentlyContinue | Out-Null
        Write-Host "✅ Enabled LongPathsEnabled for Python" -ForegroundColor Green
    }

    # Verify it worked
    $isEnabled = Test-LongPathsEnabled
    if ($isEnabled) {
        Write-Host ""
        Write-Host "🎉 Long path support successfully enabled!" -ForegroundColor Green
        Write-Host ""
        Write-Host "⚠️  IMPORTANT: You may need to restart your computer for changes to take full effect." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Next steps:" -ForegroundColor Cyan
        Write-Host "  1. Restart your computer (recommended)" -ForegroundColor White
        Write-Host "  2. Install code-puppy: uvx code-puppy -i" -ForegroundColor White
        Write-Host ""
    } else {
        Write-Host "❌ Failed to verify long path enablement" -ForegroundColor Red
        exit 1
    }

} catch {
    Write-Host "❌ Error enabling long paths: $_" -ForegroundColor Red
    exit 1
}

Write-Host "Setup complete! 🐶" -ForegroundColor Green
