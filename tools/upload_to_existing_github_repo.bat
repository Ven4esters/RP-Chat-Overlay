@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

echo ======================================================
echo  Upload a folder to an EXISTING GitHub repository
echo ======================================================
echo This copies the selected folder into the repository root, commits,
echo and pushes to the branch cloned from that repository's default branch.
echo Existing files with matching paths may be replaced.
echo Review the source folder. Never upload passwords, API keys, or secrets.
echo.

where gh >nul 2>nul || goto :nogh
where git >nul 2>nul || goto :nogit
gh auth status >nul 2>nul || goto :noauth

set "SRC=%~dp0..\dist"
if not exist "%SRC%\." set "SRC=%~dp0..\..\dist"
for %%I in ("%SRC%") do set "SRC=%%~fI"
echo Folder to upload (Enter for the release files in dist):
echo   Default: "%SRC%"
set /p "INPUT_SRC=Folder: "
if defined INPUT_SRC set "SRC=%INPUT_SRC%"
set "SRC=%SRC:"=%"
for %%I in ("%SRC%") do set "SRC=%%~fI"
if not exist "%SRC%\." goto :badsource

echo.
echo Existing GitHub repository, in OWNER/REPOSITORY format.
echo Example: Ven4esters/FiveM-Chat-Overlay
echo.
set /p "TARGET=Repository: "
if not defined TARGET goto :cancel
gh repo view "%TARGET%" --json nameWithOwner --jq .nameWithOwner >nul 2>nul
if errorlevel 1 goto :badrepo

echo.
echo Target repository: %TARGET%
echo Source folder: "%SRC%"
echo Files are copied into the repository root. Matching paths will be overwritten.
choice /c YN /n /m "Continue? [Y/N] "
if errorlevel 2 goto :cancel

set "WORK=%TEMP%\FiveMChatOverlay-upload-%RANDOM%-%RANDOM%"
echo.
echo Cloning existing repository ...
gh repo clone "%TARGET%" "%WORK%"
if errorlevel 1 goto :clonefail

echo Copying files ...
robocopy "%SRC%" "%WORK%" /E /XD .git .venv .build-venv __pycache__ node_modules .pytest_cache .ruff_cache /XF .env .env.*
if errorlevel 8 goto :copyfail

for /f "delims=" %%A in ('git -C "%WORK%" config user.name 2^>nul') do set "GIT_NAME=%%A"
for /f "delims=" %%A in ('git -C "%WORK%" config user.email 2^>nul') do set "GIT_EMAIL=%%A"
if defined GIT_NAME if defined GIT_EMAIL goto :identity_ok

echo.
echo Git needs an author identity for the commit.
if not defined GIT_NAME set /p "GIT_NAME=Your name: "
if not defined GIT_EMAIL set /p "GIT_EMAIL=Your GitHub email: "
if not defined GIT_NAME goto :identityfail
if not defined GIT_EMAIL goto :identityfail
git -C "%WORK%" config user.name "%GIT_NAME%"
git -C "%WORK%" config user.email "%GIT_EMAIL%"
if errorlevel 1 goto :identityfail

:identity_ok
git -C "%WORK%" add -A
if errorlevel 1 goto :gitfail
git -C "%WORK%" diff --cached --quiet
if not errorlevel 1 goto :nochanges

git -C "%WORK%" commit -m "Upload selected files"
if errorlevel 1 goto :gitfail
git -C "%WORK%" push origin HEAD
if errorlevel 1 goto :pushfail

echo.
echo Upload complete:
echo   https://github.com/%TARGET%
echo Local clone: "%WORK%"
echo.
pause
exit /b 0

:nogh
echo GitHub CLI (gh) was not found. Install it from https://cli.github.com/ and retry.
goto :failed
:nogit
echo Git was not found. Install Git for Windows and retry.
goto :failed
:noauth
echo GitHub CLI is not authenticated. Run: gh auth login
goto :failed
:badsource
echo Source folder does not exist: "%SRC%"
goto :failed
:badrepo
echo Repository was not found or your account cannot access it: %TARGET%
goto :failed
:clonefail
echo Could not clone the existing repository. Check access and network connectivity.
goto :failed
:copyfail
echo Copying failed. The local clone may contain partial changes: "%WORK%"
goto :failed
:identityfail
echo Could not set the Git author identity. Configure git user.name and user.email, then retry.
goto :failed
:gitfail
echo Git could not stage or commit the selected files.
goto :failed
:nochanges
echo No changes to upload; the selected files already match the repository.
echo Local clone: "%WORK%"
goto :failed
:pushfail
echo Commit was created locally, but push failed. A protected branch may require a pull request.
echo Review the local clone: "%WORK%"
goto :failed
:cancel
echo Cancelled.
exit /b 1
:failed
echo.
pause
exit /b 1
