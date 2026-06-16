@echo off
rem Сборка: src_xml/ -> шаблон .project -> компиляция -> .projectarchive.
rem Для сборщика/CI. Код возврата != 0 при ошибках компиляции.
setlocal

set "CODESYS=C:\Program Files\CODESYS 3.5.17.30\CODESYS\Common\CODESYS.exe"
set "PROFILE=CODESYS V3.5 SP17 Patch 3"
rem Шаблон с настроенным "железом" (вариант A). Здесь — текущий проект как шаблон.
set "TEMPLATE=project\V0.5\117_1_V0.5.project"
set "SRCXML=src_xml"
set "ARCHIVE=out\117_1_V0.5.projectarchive"

cd /d "%~dp0.."

"%CODESYS%" --profile="%PROFILE%" --noUI ^
  --runscript="scripts\build.py" ^
  --scriptargs:"%TEMPLATE% %SRCXML% %ARCHIVE%"

echo.
echo [run_build] exit code: %ERRORLEVEL%
endlocal
