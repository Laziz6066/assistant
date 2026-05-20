@echo off
REM Build voice-assistant portable distribution.
REM Usage: run from anywhere — this script cds to repo root automatically.
setlocal

set REPO_ROOT=%~dp0..
cd /d %REPO_ROOT%

REM Clean previous build artifacts
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Run PyInstaller
.venv\Scripts\python.exe -m PyInstaller installer\voice_assistant.spec --noconfirm
if errorlevel 1 (
    echo PyInstaller failed.
    exit /b 1
)

REM Copy user-editable configs alongside the .exe
xcopy /e /i /y config dist\voice-assistant\config\
if errorlevel 1 (
    echo Config copy failed.
    exit /b 1
)
copy /y installer\README-USER.txt dist\voice-assistant\README.txt
if errorlevel 1 (
    echo README copy failed.
    exit /b 1
)

REM Zip the result
.venv\Scripts\python.exe -c "import shutil; shutil.make_archive('dist/voice-assistant-0.1.0', 'zip', 'dist', 'voice-assistant')"
if errorlevel 1 (
    echo Zip step failed.
    exit /b 1
)

echo.
echo Build complete: dist\voice-assistant-0.1.0.zip
echo.
endlocal
