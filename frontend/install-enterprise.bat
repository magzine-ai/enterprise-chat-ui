@echo off
REM Enterprise Installation Script for Windows
REM This script installs dependencies and sets up fast-equals replacement

echo Installing Enterprise Chat UI...
echo.

REM Step 1: Install dependencies (skip scripts to avoid fast-equals error)
echo Step 1: Installing dependencies (ignoring scripts)...
call npm install --ignore-scripts
if %errorlevel% neq 0 (
    echo Warning: Some packages may have failed, continuing...
)

echo.
echo Step 2: Setting up fast-equals replacement...

REM Create directories
if not exist "node_modules\fast-equals" mkdir "node_modules\fast-equals"
if not exist "node_modules\react-smooth\node_modules" mkdir "node_modules\react-smooth\node_modules"
if not exist "node_modules\react-smooth\node_modules\fast-equals" mkdir "node_modules\react-smooth\node_modules\fast-equals"

REM Copy replacement files
if exist "fast-equals-replacement\index.js" (
    copy /Y "fast-equals-replacement\index.js" "node_modules\fast-equals\index.js" >nul
    copy /Y "fast-equals-replacement\index.js" "node_modules\react-smooth\node_modules\fast-equals\index.js" >nul
    echo   [OK] Copied index.js
)

if exist "fast-equals-replacement\index.d.ts" (
    copy /Y "fast-equals-replacement\index.d.ts" "node_modules\fast-equals\index.d.ts" >nul
    copy /Y "fast-equals-replacement\index.d.ts" "node_modules\react-smooth\node_modules\fast-equals\index.d.ts" >nul
    echo   [OK] Copied index.d.ts
)

if exist "fast-equals-replacement\package.json" (
    copy /Y "fast-equals-replacement\package.json" "node_modules\fast-equals\package.json" >nul
    copy /Y "fast-equals-replacement\package.json" "node_modules\react-smooth\node_modules\fast-equals\package.json" >nul
    echo   [OK] Copied package.json
)

echo.
echo Step 3: Running postinstall script...
call npm run postinstall

echo.
echo ========================================
echo Installation complete!
echo ========================================
echo.
echo You can now run: npm run dev
echo.

pause

