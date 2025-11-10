@echo off
REM Code Puppy Windows Setup - Batch wrapper
REM This script checks for admin privileges and runs the PowerShell setup

echo.
echo  Code Puppy Windows Setup
echo ================================
echo.

REM Check for admin privileges
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: This script requires administrator privileges.
    echo.
    echo Please right-click this file and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)

echo Running PowerShell setup script...
echo.

REM Run the PowerShell script
powershell.exe -ExecutionPolicy Bypass -File "%~dp0windows_setup.ps1"

if %errorlevel% equ 0 (
    echo.
    echo Setup completed successfully!
    echo.
) else (
    echo.
    echo Setup encountered an error.
    echo.
)

pause
