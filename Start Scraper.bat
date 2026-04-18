@echo off
setlocal EnableDelayedExpansion
title InventoryScraper

:: ===================================================================
::  InventoryScraper - One-Click Launcher (Windows)
::  Double-click this file to start the scraper dashboard.
:: ===================================================================

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "VENV_DIR=%ROOT_DIR%.venv"
set "REQUIREMENTS=%BACKEND_DIR%\requirements.txt"
set "PORT=8000"
set "URL=http://127.0.0.1:%PORT%"

echo.
echo  ===================================================
echo    InventoryScraper - Dashboard Launcher
echo  ===================================================
echo.

:: -----------------------------------------------------------
::  Step 1: Find Python 3.11
:: -----------------------------------------------------------
echo  [1/5] Checking for Python...

set "PYTHON_CMD="

:: Try 'py -3.11' first (Windows launcher, specific version)
py -3.11 --version >nul 2>&1
if !errorlevel!==0 (
    set "PYTHON_CMD=py -3.11"
    goto :python_found
)

:: Try 'python' 
python --version >nul 2>&1
if !errorlevel!==0 (
    set "PYTHON_CMD=python"
    goto :python_found
)

:: Try 'py' (any version)
py --version >nul 2>&1
if !errorlevel!==0 (
    set "PYTHON_CMD=py"
    goto :python_found
)

echo.
echo  ERROR: Python is not installed or not in PATH.
echo.
echo  Please install Python 3.11+ from https://www.python.org/downloads/
echo  Make sure to check "Add Python to PATH" during installation!
echo.
pause
exit /b 1

:python_found
for /f "tokens=*" %%v in ('!PYTHON_CMD! --version 2^>^&1') do set "PY_VERSION=%%v"
echo        OK - Found !PY_VERSION!

:: -----------------------------------------------------------
::  Step 2: Create Virtual Environment
:: -----------------------------------------------------------
echo  [2/5] Setting up virtual environment...

if exist "%VENV_DIR%\Scripts\python.exe" (
    echo        OK - Virtual environment exists
) else (
    echo        Creating virtual environment...
    !PYTHON_CMD! -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo.
        echo  ERROR: Failed to create virtual environment.
        echo.
        pause
        exit /b 1
    )
    echo        OK - Virtual environment created
)

set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

:: -----------------------------------------------------------
::  Step 3: Install Dependencies
:: -----------------------------------------------------------
echo  [3/5] Checking dependencies...

set "DEPS_MARKER=%VENV_DIR%\.deps_installed"

if exist "%DEPS_MARKER%" (
    echo        OK - Dependencies already installed
    goto :deps_done
)

echo        Installing Python packages (this may take a minute)...
"%VENV_PIP%" install -r "%REQUIREMENTS%" --quiet --disable-pip-version-check
if !errorlevel! neq 0 (
    echo.
    echo  ERROR: Failed to install dependencies.
    echo  Check your internet connection and try again.
    echo.
    pause
    exit /b 1
)

echo installed > "%DEPS_MARKER%"
echo        OK - Dependencies installed

:deps_done

:: -----------------------------------------------------------
::  Step 4: Install Playwright Browsers
:: -----------------------------------------------------------
echo  [4/5] Checking Playwright browsers...

set "PW_MARKER=%VENV_DIR%\.playwright_installed"

if exist "%PW_MARKER%" (
    echo        OK - Playwright browsers ready
    goto :pw_done
)

echo        Installing Chromium browser (one-time download, ~150MB)...
"%VENV_PYTHON%" -m playwright install chromium
if !errorlevel! neq 0 (
    echo.
    echo  ERROR: Failed to install Playwright browsers.
    echo.
    pause
    exit /b 1
)

"%VENV_PYTHON%" -m playwright install-deps chromium >nul 2>&1

echo installed > "%PW_MARKER%"
echo        OK - Playwright browsers installed

:pw_done

:: -----------------------------------------------------------
::  Step 5: Launch Server
:: -----------------------------------------------------------
echo  [5/5] Starting server...
echo.
echo  ---------------------------------------------------
echo    Dashboard will open at: %URL%
echo    Press Ctrl+C to stop the server
echo  ---------------------------------------------------
echo.

:: Open browser after a short delay
start "" cmd /c "timeout /t 3 /nobreak >nul && start %URL%"

:: Start the server (this blocks until Ctrl+C)
cd /d "%BACKEND_DIR%"
"%VENV_PYTHON%" main.py

echo.
echo  Server stopped.
echo.
pause
