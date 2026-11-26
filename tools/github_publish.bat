@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

:menu
echo ======================================================
echo  GitHub helper: upload files or publish a release
echo ======================================================
echo.
echo [U] Upload a folder to an existing repository
echo [R] Create a GitHub Release in an existing repository
echo [Q] Quit
choice /c URQ /n /m "Choose U, R, or Q: "
if errorlevel 3 goto :quit
if errorlevel 2 goto :release
if errorlevel 1 goto :upload
goto :menu

:upload
echo.
echo === Upload a folder to an EXISTING GitHub repository ===
echo Files go into the repository root; matching paths can be overwritten.
echo Review the selected folder and do not upload secrets.
echo.
where gh >nul 2>nul
if errorlevel 1 goto :upload_nogh
where git >nul 2>nul
if errorlevel 1 goto :upload_nogit
gh auth status >nul 2>nul
if errorlevel 1 goto :noauth

set "SRC=%~dp0..\dist"
if not exist "%SRC%\." set "SRC=%~dp0..\..\dist"
for %%I in ("%SRC%") do set "SRC=%%~fI"
echo Source folder (Enter uses the release files in dist):
echo   Default: "%SRC%"
set "INPUT_SRC="
set /p "INPUT_SRC=Folder: "
if defined INPUT_SRC set "SRC=%INPUT_SRC%"
set "SRC=%SRC:"=%"
for %%I in ("%SRC%") do set "SRC=%%~fI"
if not exist "%SRC%\." goto :upload_badsource

set "TARGET="
echo.
echo Existing repository in OWNER/REPOSITORY format, for example:
echo Ven4esters/FiveM-Chat-Overlay
set /p "TARGET=Repository: "
if not defined TARGET goto :menu
gh repo view "%TARGET%" --json nameWithOwner --jq .nameWithOwner >nul 2>nul
if errorlevel 1 goto :upload_badrepo

echo.
echo Target: %TARGET%
echo Source: "%SRC%"
echo The contents will be copied into the repository root.
choice /c YN /n /m "Continue? [Y/N] "
if errorlevel 2 goto :menu

set "WORK=%TEMP%\FiveMChatOverlay-upload-%RANDOM%-%RANDOM%"
echo Cloning existing repository ...
gh repo clone "%TARGET%" "%WORK%"
if errorlevel 1 goto :upload_clonefail

echo Copying files ...
robocopy "%SRC%" "%WORK%" /E /XD .git .venv .build-venv __pycache__ node_modules .pytest_cache .ruff_cache /XF .env .env.* *.exe
if errorlevel 8 goto :upload_copyfail

set "GIT_NAME="
set "GIT_EMAIL="
for /f "delims=" %%A in ('git -C "%WORK%" config user.name 2^>nul') do set "GIT_NAME=%%A"
for /f "delims=" %%A in ('git -C "%WORK%" config user.email 2^>nul') do set "GIT_EMAIL=%%A"
if defined GIT_NAME if defined GIT_EMAIL goto :upload_identity_ok
echo.
if not defined GIT_NAME set /p "GIT_NAME=Git author name: "
if not defined GIT_EMAIL set /p "GIT_EMAIL=Git author email: "
if not defined GIT_NAME goto :upload_identityfail
if not defined GIT_EMAIL goto :upload_identityfail
git -C "%WORK%" config user.name "%GIT_NAME%"
git -C "%WORK%" config user.email "%GIT_EMAIL%"
if errorlevel 1 goto :upload_identityfail

:upload_identity_ok
git -C "%WORK%" add -A
if errorlevel 1 goto :upload_gitfail
git -C "%WORK%" diff --cached --quiet
if not errorlevel 1 goto :upload_nochanges
git -C "%WORK%" commit -m "Upload selected files"
if errorlevel 1 goto :upload_gitfail
git -C "%WORK%" push origin HEAD
if errorlevel 1 goto :upload_pushfail
echo.
echo Upload complete: https://github.com/%TARGET%
echo Local clone: "%WORK%"
pause
goto :menu

:release
echo.
echo === Create a GitHub Release in an EXISTING repository ===
where gh >nul 2>nul
if errorlevel 1 goto :release_nogh
gh auth status >nul 2>nul
if errorlevel 1 goto :noauth

set "TARGET="
echo.
set /p "TARGET=Repository (OWNER/REPOSITORY): "
if not defined TARGET goto :menu
gh repo view "%TARGET%" --json nameWithOwner --jq .nameWithOwner >nul 2>nul
if errorlevel 1 goto :release_badrepo

set "TAG=v1.0.0"
set "INPUT_TAG="
set /p "INPUT_TAG=Release tag (Enter for v1.0.0): "
if defined INPUT_TAG set "TAG=%INPUT_TAG%"
set "TITLE=%TAG%"
set "INPUT_TITLE="
set /p "INPUT_TITLE=Release title (Enter for %TAG%): "
if defined INPUT_TITLE set "TITLE=%INPUT_TITLE%"

set "ASSET_DIR=%~dp0..\dist"
if not exist "%ASSET_DIR%\." set "ASSET_DIR=%~dp0..\..\dist"
for %%I in ("%ASSET_DIR%") do set "ASSET_DIR=%%~fI"
echo.
echo Asset folder (Enter uses the release files in dist):
echo   Default: "%ASSET_DIR%"
set "INPUT_DIR="
set /p "INPUT_DIR=Folder: "
if defined INPUT_DIR set "ASSET_DIR=%INPUT_DIR%"
set "ASSET_DIR=%ASSET_DIR:"=%"
for %%I in ("%ASSET_DIR%") do set "ASSET_DIR=%%~fI"
if not exist "%ASSET_DIR%\." goto :release_baddir
dir /b /a-d "%ASSET_DIR%\*" >nul 2>nul
if errorlevel 1 goto :release_noassets

echo.
choice /c YN /n /m "Generate release notes automatically? [Y/N] "
if errorlevel 2 goto :release_manualnotes
set "NOTES_MODE=generated"
set "NOTES="
goto :release_notes_done
:release_manualnotes
set "NOTES_MODE=manual"
set /p "NOTES=Release notes (one line; blank is allowed): "
:release_notes_done
echo.
choice /c YN /n /m "Mark as pre-release? [Y/N] "
if errorlevel 2 goto :release_not_prerelease
set "PRERELEASE=--prerelease"
goto :release_prerelease_done
:release_not_prerelease
set "PRERELEASE="
:release_prerelease_done

echo.
echo Repository: %TARGET%
echo Tag: %TAG%
echo Title: %TITLE%
echo Assets: "%ASSET_DIR%\*"
choice /c YN /n /m "Publish this release now? [Y/N] "
if errorlevel 2 goto :menu

echo Creating release ...
if /i "%NOTES_MODE%"=="generated" (
  gh release create "%TAG%" "%ASSET_DIR%\*" --repo "%TARGET%" --title "%TITLE%" --generate-notes %PRERELEASE%
) else (
  gh release create "%TAG%" "%ASSET_DIR%\*" --repo "%TARGET%" --title "%TITLE%" --notes "%NOTES%" %PRERELEASE%
)
if errorlevel 1 goto :release_failed
echo.
echo Release published: https://github.com/%TARGET%/releases/tag/%TAG%
pause
goto :menu

:upload_nogh
echo GitHub CLI (gh) was not found. Install it from https://cli.github.com/ and retry.
goto :show_error
:upload_nogit
echo Git was not found. Install Git for Windows and retry.
goto :show_error
:noauth
echo GitHub CLI is not authenticated. Run: gh auth login
goto :show_error
:upload_badsource
echo Source folder does not exist: "%SRC%"
goto :show_error
:upload_badrepo
echo Repository was not found or your account cannot access it: %TARGET%
goto :show_error
:upload_clonefail
echo Could not clone the existing repository. Check access and network connectivity.
goto :show_error
:upload_copyfail
echo Copying failed. The local clone may contain partial changes: "%WORK%"
goto :show_error
:upload_identityfail
echo Could not set Git author name/email.
goto :show_error
:upload_gitfail
echo Git could not stage or commit the selected files.
goto :show_error
:upload_pushfail
echo Push failed. A protected branch may require a pull request.
echo Review the local clone: "%WORK%"
goto :show_error
:upload_nochanges
echo No changes to upload; the selected files already match the repository.
echo Local clone: "%WORK%"
pause
goto :menu
:release_nogh
echo GitHub CLI (gh) was not found. Install it from https://cli.github.com/ and retry.
goto :show_error
:release_badrepo
echo Repository was not found or your account cannot access it: %TARGET%
goto :show_error
:release_baddir
echo Asset folder does not exist: "%ASSET_DIR%"
goto :show_error
:release_noassets
echo No files were found directly in: "%ASSET_DIR%"
goto :show_error
:release_failed
echo Release creation failed. Check tag, permissions, asset names, and gh output.
goto :show_error
:show_error
echo.
pause
goto :menu
:quit
echo Exiting.
exit /b 0
