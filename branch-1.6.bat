@echo off
setlocal
title RP Chat Overlay - branch develop

set BRANCH=feature/develop
set MSG=1.6: package app, module registry, bilingual comments, code cleanup

echo.
echo === Move the 1.6 rework into branch %BRANCH% ===
echo.

where git >nul 2>nul
if errorlevel 1 goto no_git

git rev-parse --is-inside-work-tree >nul 2>nul
if errorlevel 1 goto no_repo

if not exist "source\app\modules.py" goto no_files

rem --- old flat modules must be gone, otherwise git keeps them on the branch
set LEFT=
for %%F in (common.py engine.py translator.py slang.py translit.py langs.py i18n.py autoplan.py gamesend.py hotkey.py overlay.py settings_ui.py ui_lang.py glossary_data.py) do if exist "source\%%F" set LEFT=1
if exist "source\langpacks\__init__.py" set LEFT=1
if defined LEFT goto old_files

echo [1/4] current branch:
git rev-parse --abbrev-ref HEAD

echo [2/4] switch to %BRANCH%
git rev-parse -q --verify refs/heads/%BRANCH% >nul 2>nul
if not errorlevel 1 goto have_branch
git checkout -b %BRANCH%
if errorlevel 1 goto fail
goto branch_ready
:have_branch
echo      branch already exists, switching to it
git checkout %BRANCH%
if errorlevel 1 goto fail
:branch_ready

echo [3/4] stage everything
git add -A
echo      changed files:
git status --short | find /c /v "" 

echo [4/4] commit and push
git diff --cached --quiet
if not errorlevel 1 goto nothing
git commit -m "%MSG%"
if errorlevel 1 goto fail
goto push
:nothing
echo      nothing to commit, the branch already holds the rework
:push
git push -u origin %BRANCH%
if errorlevel 1 goto fail

echo.
echo Done. main is untouched, the rework lives in %BRANCH%.
echo.
echo Next steps:
echo   * keep working:   just commit and push on this branch
echo   * back to main:   git checkout main
echo   * merge later:    git checkout main ^&^& git merge --no-ff %BRANCH%
echo.
pause
exit /b 0

:no_git
echo [x] git is not installed or not in PATH.
goto end_pause

:no_repo
echo [x] this folder is not a git repository.
echo     run the file from the project root (the folder with .git, source and dist).
goto end_pause

:no_files
echo [x] source\app\modules.py is not found - the 1.6 files are not copied yet.
echo     unpack RP-Chat-Overhaul.zip over the project first.
goto end_pause

:old_files
echo [x] old flat modules are still in source\ - delete them first:
echo.
echo     del source\common.py source\engine.py source\translator.py source\slang.py
echo     del source\translit.py source\langs.py source\i18n.py source\autoplan.py
echo     del source\gamesend.py source\hotkey.py source\overlay.py source\settings_ui.py
echo     del source\ui_lang.py source\glossary_data.py
echo     rmdir /s /q source\langpacks
echo.
echo     everything now lives in source\app\
goto end_pause

:fail
echo.
echo [x] something went wrong, see the output above.
echo     check: git status, gh auth status, push rights to the repository.

:end_pause
echo.
pause
exit /b 1
