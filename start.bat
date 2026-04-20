@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

REM ============================================================
REM   CrawlPhotos - One-click Start Script
REM   Usage:
REM     start.bat       Start all services
REM     start.bat stop   Stop all services
REM ============================================================

set "ROOT_DIR=%~dp0"
set "BACKEND_PORT=8000"
set "FRONTEND_PORT=3000"

if /i "%1"=="stop" goto :stop
if /i "%1"=="--stop" goto :stop

echo.
echo ============================================
echo   CrawlPhotos - Starting services...
echo ============================================

cd /d "%ROOT_DIR%"

REM ---- Stop old processes on target ports ----
call :cleanup_port %BACKEND_PORT%
call :cleanup_port %FRONTEND_PORT%

REM ---- Step 1: Start Backend API ----
echo.
echo [1/2] Starting Backend API (port %BACKEND_PORT%) ...
start "CrawlPhotos-API" cmd /c python start_api.py
timeout /t 5 /nobreak >nul
call :wait_ready %BACKEND_PORT% 10
if errorlevel 1 (
    echo [WARN] Backend may not be ready yet. Check the API window.
) else (
    echo [OK] Backend ready at http://127.0.0.1:%BACKEND_PORT%
)

REM ---- Step 2: Start Frontend ----
echo.
echo [2/2] Starting Frontend (port %FRONTEND_PORT%) ...
start "CrawlPhotos-Frontend" cmd /c node serve_web.js
timeout /t 2 /nobreak >nul
call :wait_ready %FRONTEND_PORT% 5
if errorlevel 1 (
    echo [WARN] Frontend may not be ready yet. Check the frontend window.
) else (
    echo [OK] Frontend ready at http://localhost:%FRONTEND_PORT%
)

REM ---- Done ----
echo.
echo ============================================
echo   All services started!
echo ============================================
echo   Backend API:  http://127.0.0.1:%BACKEND_PORT%
echo   Frontend:     http://localhost:%FRONTEND_PORT%
echo   API Docs:     http://127.0.0.1:%BACKEND_PORT%/docs
echo ============================================
echo.
echo Press any key to open browser...
pause >nul
start http://localhost:%FRONTEND_PORT%
goto :eof


REM ============================================================
REM   STOP all services
REM ============================================================
:stop
echo Stopping services...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%BACKEND_PORT%" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1 && echo   Killed backend PID %%a
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%FRONTEND_PORT%" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1 && echo   Killed frontend PID %%a
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1 && echo   Killed vite PID %%a
)
echo Done.
goto :eof


REM ============================================================
REM   Cleanup process on a port
REM ============================================================
:cleanup_port
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%1" ^| findstr "LISTENING"') do (
    taskkill /PID %%p /F >nul 2>&1
)
exit /b 0


REM ============================================================
REM   Wait for port to be listening (max N seconds)
REM ============================================================
:wait_ready
set /a _cnt=0
:loop_wait
netstat -ano | findstr ":%1" | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 exit /b 0
set /a _cnt+=1
if %_cnt% GEQ %2 exit /b 1
timeout /t 1 /nobreak >nul
goto loop_wait
