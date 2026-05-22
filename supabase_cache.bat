@echo off
setlocal

cd /d "%~dp0"
title Stake-GPT Supabase Cache Cleanup

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Could not find .venv\Scripts\python.exe
  echo Run the project setup first, then try this cleanup again.
  echo.
  pause
  exit /b 1
)

if not exist ".env" (
  echo ERROR: Could not find .env
  echo The cleanup needs local Supabase settings in C:\Users\farne\Desktop\AZP\.env
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m app.supabase_cache %*
set EXIT_CODE=%ERRORLEVEL%

echo.
if not "%EXIT_CODE%"=="0" (
  echo Cleanup failed with code %EXIT_CODE%.
)
pause
exit /b %EXIT_CODE%
