@echo off
rem Экспорт кода CODESYS (POU/DUT/GVL) -> PLCopen XML в src_xml/.
rem Запускать из корня репозитория PLC или двойным кликом.
setlocal

set "CODESYS=C:\Program Files\CODESYS 3.5.17.30\CODESYS\Common\CODESYS.exe"
rem Имя профиля подтверди: Окно "About" в CODESYS или папка профилей.
set "PROFILE=CODESYS V3.5 SP17 Patch 3"
set "PROJECT=project\V0.5\117_1_V0.5.project"
set "OUTDIR=src_xml"

rem Перейти в корень репо (родитель папки scripts)
cd /d "%~dp0.."

"%CODESYS%" --profile="%PROFILE%" --noUI ^
  --runscript="scripts\export_xml.py" ^
  --scriptargs:"%PROJECT% %OUTDIR%"

echo.
echo [run_export] exit code: %ERRORLEVEL%
endlocal
