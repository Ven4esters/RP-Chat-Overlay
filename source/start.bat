@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
REM --- if a ready exe exists (..\dist or next to this file), just run it ---
if exist "%ROOT%..\dist\RPChatOverlay.exe" (
    start "" "%ROOT%..\dist\RPChatOverlay.exe"
    exit /b 0
)
if exist "%ROOT%RPChatOverlay.exe" (
    start "" "%ROOT%RPChatOverlay.exe"
    exit /b 0
)

if not exist "%ROOT%data" mkdir "%ROOT%data"
if not exist "%ROOT%logs" mkdir "%ROOT%logs"

if exist "%ROOT%requirements.txt" goto :req_ok
> "%ROOT%requirements.txt" echo deep-translator==1.11.4
>> "%ROOT%requirements.txt" echo PySide6-Essentials^>=6.7,^<7
:req_ok

echo Looking for Python 3.12 ...
call :try "%ROOT%runtime\python\python.exe"
call :try_py
for /f "delims=" %%P in ('where python 2^>nul') do call :try "%%P"
call :try "%LocalAppData%\Programs\Python\Python312\python.exe"
call :try "%ProgramFiles%\Python312\python.exe"
if not defined PYEXE call :install_local
if not defined PYEXE goto :nopython
echo Using Python: %PYEXE%

if not exist "%VENV%\Scripts\python.exe" goto :mkvenv
call :ver "%VENV%\Scripts\python.exe"
if not errorlevel 1 goto :venv_ok
echo Existing .venv is not Python 3.12, recreating ...
rmdir /s /q "%VENV%"
:mkvenv
echo Creating .venv ...
"%PYEXE%" -m venv "%VENV%"
if errorlevel 1 goto :venvfail
:venv_ok

fc /b "%ROOT%requirements.txt" "%VENV%\requirements.installed" >nul 2>nul
if not errorlevel 1 goto :deps_ok
echo Installing libraries (first run takes a few minutes) ...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip >nul 2>nul
"%VENV%\Scripts\python.exe" -m pip install -r "%ROOT%requirements.txt"
if errorlevel 1 goto :pipfail
copy /y "%ROOT%requirements.txt" "%VENV%\requirements.installed" >nul
:deps_ok

"%VENV%\Scripts\python.exe" -c "import PySide6.QtWidgets, deep_translator" 2> "%ROOT%logs\import_check.txt"
if errorlevel 1 goto :importfail

REM --- run without console window (errors are written to logs\app.log) ---
start "" "%VENV%\Scripts\pythonw.exe" "%ROOT%main.py"
REM --- for debugging with a console, comment the line above and use this one:
REM "%VENV%\Scripts\python.exe" "%ROOT%main.py" & pause
exit /b 0

:nopython
echo.
echo Python 3.12 was not found and could not be installed automatically.
echo Install it manually from https://www.python.org/downloads/windows/
echo (Windows installer 64-bit, 3.12.x) and run start.bat again.
pause
exit /b 1

:venvfail
echo.
echo Could not create .venv. Delete the .venv folder and try again.
pause
exit /b 1

:pipfail
echo.
echo Library installation failed. Check your internet connection and run start.bat again.
pause
exit /b 1

:importfail
echo.
echo PySide6 / deep_translator failed to import. Details: logs\import_check.txt
echo If you see "DLL load failed", install the Visual C++ Redistributable:
echo https://aka.ms/vs/17/release/vc_redist.x64.exe
pause
exit /b 1

REM ================= subroutines =================

:ver
"%~1" -c "import sys;sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>nul
if errorlevel 1 exit /b 1
exit /b 0

:try
if defined PYEXE exit /b 0
set "C=%~1"
if not exist "%C%" exit /b 0
echo "%C%" | find /i "WindowsApps" >nul && exit /b 0
call :ver "%C%"
if errorlevel 1 goto :try_skip
echo Candidate: %C% OK
set "PYEXE=%C%"
exit /b 0
:try_skip
echo Candidate: %C% - not Python 3.12, skipped
exit /b 0

:try_py
if defined PYEXE exit /b 0
where py >nul 2>nul || exit /b 0
py -3.12 -c "import sys;print(sys.executable)" > "%TEMP%\pyexe.txt" 2>nul
if errorlevel 1 exit /b 0
set "PYTMP="
set /p PYTMP=<"%TEMP%\pyexe.txt"
if not "%PYTMP%"=="" call :try "%PYTMP%"
exit /b 0

:install_local
set "PYINST=%TEMP%\python-3.12.8-amd64.exe"
echo Python 3.12 not found. Downloading Python 3.12.8 from python.org ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile '%PYINST%'"
if errorlevel 1 exit /b 0
echo Installing into %ROOT%runtime\python ...
start /wait "" "%PYINST%" /quiet InstallAllUsers=0 TargetDir="%ROOT%runtime\python" Include_launcher=0 Include_test=0 Include_tcltk=0 Include_doc=0 PrependPath=0 Shortcuts=0 AssociateFiles=0
call :try "%ROOT%runtime\python\python.exe"
exit /b 0