@echo off
rem Сборка: src_xml/ -> шаблон .project -> компиляция -> .projectarchive.
rem Для сборщика/CI. Код возврата != 0 при ошибках компиляции.
setlocal EnableDelayedExpansion

set "CODESYS=C:\Program Files\CODESYS 3.5.17.30\CODESYS\Common\CODESYS.exe"
set "PROFILE=CODESYS V3.5 SP17 Patch 3"
rem Шаблон с настроенным "железом" (вариант A). Здесь — текущий проект как шаблон.
set "TEMPLATE=project\static_torsion.project"
set "SRCXML=src_xml"
set "ARCHIVE=out\static_torsion.projectarchive"

cd /d "%~dp0.."

rem Вывод (в т.ч. ошибки скрипта) пишем в build.log — окно закрывается, лог остаётся.
"%CODESYS%" --profile="%PROFILE%" --noUI ^
  --runscript="scripts\build.py" ^
  --scriptargs:"%TEMPLATE% %SRCXML% %ARCHIVE%" > build.log 2>&1

set "RC=%ERRORLEVEL%"

rem --- ВЕРДИКТ ПО ЛОГУ ---
rem Метка severity 'Error:' в выводе ScriptEngine — ASCII и регистрозависима,
rem поэтому ожидаемые пропуски железа 'IMPORT ERROR:' (заглавными) НЕ считаются.
set "ERRCOUNT=0"
for /f %%C in ('findstr /C:"Error:" build.log ^| find /c /v ""') do set "ERRCOUNT=%%C"

rem Падение самого скрипта тоже = провал.
findstr /C:"BUILD FAILED" build.log >nul && set "RC=1"

if not "!ERRCOUNT!"=="0" (
  echo [run_build] КОМПИЛЯЦИЯ ПРОВАЛЕНА: !ERRCOUNT! строк уровня Error ^(см. build.log^)
  if exist "%ARCHIVE%" del /q "%ARCHIVE%"
  set "RC=1"
) else (
  echo [run_build] компиляция без ошибок уровня Error
)

echo [run_build] exit code: !RC!  ^(полный вывод в build.log^)
endlocal & exit /b %RC%
