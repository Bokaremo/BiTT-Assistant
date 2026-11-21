@echo off
rem Builds the public teacher folder, portable app, and installer.
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set PY=python
py -3.11 -c "print(1)" >nul 2>nul && set PY=py -3.11

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtual environment...
  %PY% -m venv .venv || goto fail
)
set "VENV_PY=%CD%\.venv\Scripts\python.exe"

echo [2/4] Installing packages...
"%VENV_PY%" -m pip install -r requirements.txt || goto fail

echo [2b/4] Cleaning old build...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

echo [3/4] Running tests...
"%VENV_PY%" -m pytest -q tests || goto testfail

echo [4/5] Building the general app folder...
"%VENV_PY%" -m PyInstaller --noconfirm --clean --noupx --windowed --name BittAssistant ^
  --icon "%CD%\assets\bitt.ico" ^
  --add-data "biit\web;biit\web" ^
  --hidden-import biit ^
  --hidden-import biit.server ^
  --hidden-import biit.sections ^
  --hidden-import biit.roster ^
  --hidden-import biit.config ^
  --hidden-import biit.naming ^
  --hidden-import biit.drives ^
  --hidden-import biit.treegen ^
  --hidden-import biit.transfers ^
  --hidden-import biit.deploy ^
  --hidden-import biit.reports ^
  --hidden-import biit.maintenance ^
  --hidden-import biit.foldericon ^
  --hidden-import biit.protection ^
  --hidden-import biit.projectforms ^
  --hidden-import biit.studentcards ^
  --collect-submodules uvicorn ^
  --collect-all pdfplumber ^
  --collect-all pdfminer ^
  run.py || goto fail

echo.
echo Folder build ready: dist\BittAssistant\BittAssistant.exe

echo [5/5] Building the general single-file portable executable...
if not exist "build\portable" mkdir "build\portable"
"%VENV_PY%" -m PyInstaller --noconfirm --clean --noupx --windowed --onefile ^
  --distpath "dist" --workpath "build\portable" --specpath "build\portable" ^
  --name BittAssistant-Portable ^
  --icon "%CD%\assets\bitt.ico" ^
  --add-data "%CD%\biit\web;biit\web" ^
  --hidden-import biit ^
  --hidden-import biit.server ^
  --hidden-import biit.sections ^
  --hidden-import biit.roster ^
  --hidden-import biit.config ^
  --hidden-import biit.naming ^
  --hidden-import biit.drives ^
  --hidden-import biit.treegen ^
  --hidden-import biit.transfers ^
  --hidden-import biit.deploy ^
  --hidden-import biit.reports ^
  --hidden-import biit.maintenance ^
  --hidden-import biit.foldericon ^
  --hidden-import biit.protection ^
  --hidden-import biit.projectforms ^
  --hidden-import biit.studentcards ^
  --collect-submodules uvicorn ^
  --collect-all pdfplumber ^
  --collect-all pdfminer ^
  run.py || goto fail

echo Portable single-file ready: dist\BittAssistant-Portable.exe

set "ISCC="
if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC goto noinno
"%ISCC%" installer.iss || goto fail
echo Installer ready: dist\BittAssistant-Setup.exe
goto done

:noinno
echo Inno Setup not found - installer skipped. Install Inno Setup 6 or 7 and run build.bat again.
goto done

:testfail
echo.
echo TESTS FAILED - build stopped.
echo A failing import here means a module is missing from the biit folder.
echo Fix the tests first, then run build.bat again.
pause
exit /b 1

:fail
echo.
echo BUILD FAILED - read the messages above.
pause
exit /b 1

:done
pause


