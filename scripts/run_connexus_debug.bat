@echo off
REM Connexus Debug - Automated Runner for Windows Agent
REM Doc the Puppy 🐶

echo ================================================================================
echo Connexus UI Automation Debug - Automated Mode
echo ================================================================================
echo.

REM Check if comtypes is installed
python -c "import comtypes" 2>nul
if errorlevel 1 (
    echo [ERROR] comtypes not installed!
    echo.
    echo Installing comtypes...
    pip install comtypes
    if errorlevel 1 (
        echo [FAILED] Could not install comtypes
        exit /b 1
    )
    echo [OK] comtypes installed
    echo.
)

echo [INFO] Make sure Connexus.exe is running and in foreground!
echo [INFO] Starting in 3 seconds...
ping 127.0.0.1 -n 4 > nul

echo.
echo ================================================================================
echo Step 1: Full Tree Analysis
echo ================================================================================
echo.

python scripts/debug_connexus_tree.py --auto --output connexus_tree_debug.json
if errorlevel 1 (
    echo.
    echo [FAILED] Tree walker failed!
    exit /b 1
)

echo.
echo ================================================================================
echo Step 2: List All AutomationIds
echo ================================================================================
echo.

python scripts/debug_connexus_quick.py --list-all-ids --max-results 50
set QUICKFINDER_EXIT=%errorlevel%

echo.
echo ================================================================================
echo SUMMARY
echo ================================================================================
echo.

if %QUICKFINDER_EXIT% equ 0 (
    echo [SUCCESS] Found elements with AutomationId!
    echo [INFO] Check connexus_tree_debug.json for full details
) else (
    echo [WARNING] No elements with AutomationId found
    echo [INFO] Connexus might not use AutomationIds
    echo [INFO] Check connexus_tree_debug.json for Name/ClassName properties
)

echo.
echo [OK] Debug complete
echo [FILE] connexus_tree_debug.json
echo.

exit /b 0
