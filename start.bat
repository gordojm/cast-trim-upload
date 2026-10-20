@echo off
rem Double-click to start Cast Trim Upload. It opens in your browser.
rem Keep this window open while you use the app; close it to stop the app.
cd /d "%~dp0"
title Cast Trim Upload

if not exist ".venv\Scripts\cast-trim-upload.exe" (
  echo The app is not installed yet. Follow "Install once" in README.md, then run this again.
  pause
  exit /b 1
)
if not exist "frontend\dist\index.html" (
  echo The web interface is not built yet. In a terminal run:
  echo   cd frontend
  echo   npm install
  echo   npm run build
  pause
  exit /b 1
)

".venv\Scripts\cast-trim-upload.exe"
rem Keep the window open on errors so the message can be read.
if errorlevel 1 pause
