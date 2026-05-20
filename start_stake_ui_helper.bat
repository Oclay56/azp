@echo off
setlocal

cd /d "%~dp0"
title AZP Stake UI Helper

echo AZP Stake UI Helper
echo -------------------
echo This window connects your PC to the Custom GPT through Supabase.
echo Leave it open while asking GPT for UI-backed Stake SGM boards.
echo Close this window or press Ctrl+C when you are done.
echo.

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Could not find .venv\Scripts\python.exe
  echo Run the project setup first, then try this launcher again.
  echo.
  pause
  exit /b 1
)

if not exist ".env" (
  echo ERROR: Could not find .env
  echo The helper needs local Supabase settings in C:\Users\farne\Desktop\AZP\.env
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m app.local_stake_helper

echo.
echo AZP Stake UI Helper stopped.
pause
