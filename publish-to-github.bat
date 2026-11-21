@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

set "REPO_URL=https://github.com/Bokaremo/BiTT-Assistant.git"
for %%I in ("%~dp0..") do set "PARENT=%%~fI"
set "CLONE_DIR=%PARENT%\BiTT-Assistant-publish"

where git >nul 2>nul || (echo Git غير مثبت. ثبّت Git for Windows ثم أعد المحاولة.& pause & exit /b 1)
if exist "%CLONE_DIR%" (echo مجلد النشر موجود بالفعل: "%CLONE_DIR%"& echo انقله أو احذفه يدويًا ثم أعد تشغيل هذا الملف.& pause & exit /b 1)

echo [1/5] استنساخ المستودع...
git clone "%REPO_URL%" "%CLONE_DIR%" || goto fail

echo [2/5] نسخ ملفات النسخة العامة...
robocopy "%~dp0." "%CLONE_DIR%" /E /XD .git .venv build dist dist-owner __pycache__ .pytest_cache /XF *.pyc || if errorlevel 8 goto fail
if exist "%CLONE_DIR%\BiTT-Assistant-public-source.zip" del "%CLONE_DIR%\BiTT-Assistant-public-source.zip"

pushd "%CLONE_DIR%"
git config credential.credentialStore dpapi

echo [3/5] تجهيز الملفات...
git add -A || goto fail_pop
git diff --cached --quiet
if not errorlevel 1 (
  echo الملفات الموجودة في المستودع مطابقة للنسخة العامة؛ لا توجد تغييرات جديدة.
  popd
  pause
  exit /b 0
)

for /f "delims=" %%A in ('git config user.name') do set "COMMIT_NAME=%%A"
for /f "delims=" %%A in ('git config user.email') do set "COMMIT_EMAIL=%%A"
if not defined COMMIT_NAME set "COMMIT_NAME=Bokaremo"
echo(!COMMIT_EMAIL!| findstr /c:"@" >nul
if errorlevel 1 (
  echo أدخل الاسم والبريد اللذين تريد ظهورهما في سجل التعديلات.
  set /p "COMMIT_NAME=اسم صاحب التعديل [%COMMIT_NAME%]: "
  if not defined COMMIT_NAME set "COMMIT_NAME=Bokaremo"
  set /p "COMMIT_EMAIL=بريد GitHub أو بريد noreply المرتبط بحسابك: "
  echo(!COMMIT_EMAIL!| findstr /c:"@" >nul
  if errorlevel 1 (echo البريد غير صالح.& goto fail_pop)
  git config user.name "!COMMIT_NAME!" || goto fail_pop
  git config user.email "!COMMIT_EMAIL!" || goto fail_pop
)

echo [4/5] إنشاء سجل التعديل...
git commit -m "Publish public teacher edition" || goto fail_pop

echo [5/5] رفع الملفات إلى GitHub...
git push origin HEAD || goto fail_pop

echo تم رفع المصدر العام إلى %REPO_URL%
popd
pause
exit /b 0

:fail_pop
popd
:fail
echo تعذر إكمال النشر. راجع رسالة Git أعلاه ثم أعد المحاولة.
pause
exit /b 1

