@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul

echo ======================================================
echo  Create a GitHub Release and upload its files
echo ======================================================
echo This publishes a release in an EXISTING GitHub repository.
echo Check the selected folder carefully before publishing.
echo.

where gh >nul 2>nul || goto :nogh
gh auth status >nul 2>nul || goto :noauth

set "TARGET="
echo GitHub repository, in OWNER/REPOSITORY format.
echo Example: Ven4esters/FiveM-Chat-Overlay
set /p "TARGET=Repository: "
if not defined TARGET goto :cancel
gh repo view "%TARGET%" --json nameWithOwner --jq .nameWithOwner >nul 2>nul
if errorlevel 1 goto :badrepo

set "TAG=v1.0.0"
echo.
set /p "INPUT_TAG=Release tag (Enter for v1.0.0): "
if defined INPUT_TAG set "TAG=%INPUT_TAG%"
set "TITLE=%TAG%"
set /p "INPUT_TITLE=Release title (Enter to use %TAG%): "
if defined INPUT_TITLE set "TITLE=%INPUT_TITLE%"

echo.
set "ASSET_DIR=%~dp0..\dist"
if not exist "%ASSET_DIR%\." set "ASSET_DIR=%~dp0..\..\dist"
for %%I in ("%ASSET_DIR%") do set "ASSET_DIR=%%~fI"
echo Asset folder (Enter for the release files in dist):
echo   Default: "%ASSET_DIR%"
set /p "INPUT_DIR=Folder: "
if defined INPUT_DIR set "ASSET_DIR=%INPUT_DIR%"
set "ASSET_DIR=%ASSET_DIR:"=%"
for %%I in ("%ASSET_DIR%") do set "ASSET_DIR=%%~fI"
if not exist "%ASSET_DIR%\." goto :baddir
dir /b /a-d "%ASSET_DIR%\*" >nul 2>nul
if errorlevel 1 goto :noassets

echo.
echo [Y]es: let GitHub generate release notes; [N]o: enter notes manually.
choice /c YN /n /m "Generate notes automatically? [Y/N] "
if errorlevel 2 goto :manualnotes
set "NOTES_MODE=generated"
goto :notes_done
:manualnotes
set "NOTES_MODE=manual"
set "NOTES="
set /p "NOTES=Release notes (one line; may be blank): "
:notes_done

echo.
echo Mark this as a pre-release?
choice /c YN /n /m "Pre-release? [Y/N] "
set "PRERELEASE="
if not errorlevel 2 set "PRERELEASE=--prerelease"

echo.
echo Repository: %TARGET%
echo Tag: %TAG%
echo Title: %TITLE%
echo Files: "%ASSET_DIR%\*"
choice /c YN /n /m "Create and publish this release now? [Y/N] "
if errorlevel 2 goto :cancel

echo.
echo Creating release ...
if /i "%NOTES_MODE%"=="generated" (
  gh release create "%TAG%" "%ASSET_DIR%\*" --repo "%TARGET%" --title "%TITLE%" --generate-notes %PRERELEASE%
) else (
  gh release create "%TAG%" "%ASSET_DIR%\*" --repo "%TARGET%" --title "%TITLE%" --notes "%NOTES%" %PRERELEASE%
)
if errorlevel 1 goto :releasefail

echo.
echo Release published successfully.
echo Open: https://github.com/%TARGET%/releases/tag/%TAG%
echo.
pause
exit /b 0

:nogh
echo GitHub CLI (gh) was not found. Install it from https://cli.github.com/ and retry.
goto :failed
:noauth
echo GitHub CLI is not authenticated. Run: gh auth login
goto :failed
:badrepo
echo Repository was not found or your account cannot access it: %TARGET%
goto :failed
:baddir
echo Asset folder does not exist: "%ASSET_DIR%"
goto :failed
:noassets
echo No files were found directly in: "%ASSET_DIR%"
goto :failed
:releasefail
echo Release creation failed. Check the tag, permissions, asset file names, and gh output.
goto :failed
:cancel
echo Cancelled.
exit /b 1
:failed
echo.
pause
exit /b 1
