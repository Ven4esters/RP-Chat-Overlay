@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "ROOT=%~dp0"
set "BV=%ROOT%.build-venv"
set "PYEXE="
set "EXE=%ROOT%..\dist\FiveMChatOverlay.exe"

echo ============================================
echo  FiveM Chat Overlay - Windows release build
echo ============================================
echo.

REM ---- 1. Find Python 3.12 ----
call :try "%ROOT%runtime\python\python.exe"
call :try_py
for /f "delims=" %%P in ('where python 2^>nul') do call :try "%%P"
call :try "%LocalAppData%\Programs\Python\Python312\python.exe"
call :try "%ProgramFiles%\Python312\python.exe"
if not defined PYEXE goto :nopython
echo Using Python: %PYEXE%
echo.

REM ---- 2. Create or validate the build environment ----
if not exist "%BV%\Scripts\python.exe" goto :mkvenv
"%BV%\Scripts\python.exe" -c "import sys;sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>nul
if not errorlevel 1 goto :venv_ok
echo Recreating build environment ...
rmdir /s /q "%BV%"
:mkvenv
echo Creating build environment ...
"%PYEXE%" -m venv "%BV%"
if errorlevel 1 goto :venvfail
:venv_ok

REM ---- 3. Install dependencies and PyInstaller ----
echo Installing dependencies and PyInstaller ...
"%BV%\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
"%BV%\Scripts\python.exe" -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 goto :pipfail
"%BV%\Scripts\python.exe" -m pip install --upgrade pyinstaller
if errorlevel 1 goto :pipfail

REM ---- 4. Build the Windows executable ----
echo.
echo Building FiveMChatOverlay.exe ...
"%BV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath "%ROOT%..\dist" FiveMChatOverlay.spec
if errorlevel 1 goto :buildfail
if not exist "%EXE%" goto :buildfail

REM ---- 5. Write the README TXT and matching checksum sidecars ----
echo.
"%BV%\Scripts\python.exe" "%ROOT%tools\write_release_info.py" "%EXE%"
if errorlevel 1 goto :infofail

echo.
echo Release files are next to the EXE in the dist folder:
echo   FiveMChatOverlay.exe
echo   FiveMChatOverlay-README.txt
echo   FiveMChatOverlay.exe.md5
echo   FiveMChatOverlay.exe.sha256
echo.
echo VirusTotal is NOT scanned by this build script. Upload the exact EXE,
echo wait for a real report, and verify it against the SHA-256 in the TXT file.
pause
exit /b 0

:nopython
echo.
echo Python 3.12 was not found.
echo Install Python 3.12 x64 from https://www.python.org/downloads/windows/
echo then run build_exe.bat again.
pause
exit /b 1

:venvfail
echo.
echo Could not create .build-venv. Delete that folder and try again.
pause
exit /b 1

:pipfail
echo.
echo Dependency installation failed. Check the internet connection and try again.
pause
exit /b 1

:buildfail
echo.
echo Build failed. Check PyInstaller output and build\FiveMChatOverlay\warn-FiveMChatOverlay.txt.
pause
exit /b 1

:infofail
echo.
echo The EXE exists, but README or checksum generation failed.
echo Check Python output and write permissions for the dist folder.
pause
exit /b 1

REM ================= subroutines =================
:try
if defined PYEXE exit /b 0
set "C=%~1"
if not exist "%C%" exit /b 0
echo "%C%" | find /i "WindowsApps" >nul && exit /b 0
"%C%" -c "import sys;sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>nul
if errorlevel 1 exit /b 0
set "PYEXE=%C%"
exit /b 0

:try_py
if defined PYEXE exit /b 0
where py >nul 2>nul || exit /b 0
py -3.12 -c "import sys;print(sys.executable)" > "%TEMP%\fiveMChatOverlay_pyexe.txt" 2>nul
if errorlevel 1 exit /b 0
set "PYTMP="
set /p PYTMP=<"%TEMP%\fiveMChatOverlay_pyexe.txt"
if defined PYTMP call :try "%PYTMP%"
exit /b 0
