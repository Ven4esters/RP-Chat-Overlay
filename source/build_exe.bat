@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "ROOT=%~dp0"
set "BV=%ROOT%.build-venv"
set "PYEXE="

echo ============================================
echo  RP Chat Overlay - building RPChatOverlay.exe
echo ============================================
echo.

REM ---- 1. Python 3.12 ----
call :try "%ROOT%runtime\python\python.exe"
call :try_py
for /f "delims=" %%P in ('where python 2^>nul') do call :try "%%P"
call :try "%LocalAppData%\Programs\Python\Python312\python.exe"
call :try "%ProgramFiles%\Python312\python.exe"
if not defined PYEXE goto :nopython
echo Using Python: %PYEXE%
echo.

REM ---- 2. build environment ----
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

REM ---- 3. libraries + PyInstaller ----
echo Installing libraries and PyInstaller (a few minutes) ...
"%BV%\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
"%BV%\Scripts\python.exe" -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 goto :pipfail
"%BV%\Scripts\python.exe" -m pip install --upgrade pyinstaller
if errorlevel 1 goto :pipfail

REM ---- 4. build ----
echo.
echo Building exe ...
"%BV%\Scripts\python.exe" -m PyInstaller --noconfirm --clean --distpath "%ROOT%..\dist" RPChatOverlay.spec
if errorlevel 1 goto :buildfail

echo.
if not exist "%ROOT%..\dist\RPChatOverlay.exe" goto :buildfail
echo Done: %ROOT%..\dist\RPChatOverlay.exe
echo.
REM ---------- checksums of the built exe ----------
set "EXE=%ROOT%..\dist\RPChatOverlay.exe"
set "SHA="
set "MD5="
for /f "usebackq tokens=*" %%H in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%EXE%').Hash.ToLower()"`) do set "SHA=%%H"
for /f "usebackq tokens=*" %%H in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-FileHash -Algorithm MD5 -LiteralPath '%EXE%').Hash.ToLower()"`) do set "MD5=%%H"
if not defined SHA goto :hash_plain
powershell -NoProfile -ExecutionPolicy Bypass -Command "Write-Host '  SHA-256  ' -NoNewline -ForegroundColor DarkGray; Write-Host '%SHA%' -ForegroundColor Green"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Write-Host '  MD5      ' -NoNewline -ForegroundColor DarkGray; Write-Host '%MD5%' -ForegroundColor Cyan"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$f=Get-Item -LiteralPath '%EXE%'; Write-Host '  Size     ' -NoNewline -ForegroundColor DarkGray; Write-Host ('{0:N0} bytes ({1:N1} MiB)' -f $f.Length,($f.Length/1MB)) -ForegroundColor Yellow"
goto :hash_done
:hash_plain
REM no PowerShell here - certutil without colour
for /f "skip=1 delims=" %%H in ('certutil -hashfile "%EXE%" SHA256') do if not defined SHA set "SHA=%%H"
for /f "skip=1 delims=" %%H in ('certutil -hashfile "%EXE%" MD5') do if not defined MD5 set "MD5=%%H"
echo   SHA-256  %SHA%
echo   MD5      %MD5%
:hash_done
echo.
echo VirusTotal for this build: https://www.virustotal.com/gui/file/%SHA%
echo.
echo The exe is self-contained: Python and PySide6 are inside.
echo Give players only RPChatOverlay.exe - no installation needed.
echo First start creates data\ and logs\ next to the exe.
echo.
echo To publish it: use GitHub Releases, not a repo upload.
echo GitHub web upload allows 25 MB only, Releases allow up to 2 GB per file.
echo (Repo -^> Releases -^> Draft a new release -^> Attach binaries)
pause
exit /b 0

:nopython
echo.
echo Python 3.12 was not found.
echo Install it from https://www.python.org/downloads/windows/ (3.12.x, 64-bit),
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
echo Library installation failed. Check the internet connection and try again.
pause
exit /b 1

:buildfail
echo.
echo Build failed. Details are above; the log is in build\RPChatOverlay\warn-RPChatOverlay.txt
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
py -3.12 -c "import sys;print(sys.executable)" > "%TEMP%\pyexe_build.txt" 2>nul
if errorlevel 1 exit /b 0
set "PYTMP="
set /p PYTMP=<"%TEMP%\pyexe_build.txt"
if defined PYTMP call :try "%PYTMP%"
exit /b 0
