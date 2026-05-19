@echo off
setlocal enableextensions

set "LOG=d:\PFE_final\mock database\etl_mock_to_dw_step1.log"
echo ==== [%DATE% %TIME%] ETL_Mock_To_DW Step1 ====>>"%LOG%"
echo Running as: %USERNAME%>>"%LOG%"

set "SCRIPT=%ETL_SCRIPT_PATH%"
if "%SCRIPT%"=="" set "SCRIPT=d:\PFE_final\mock database\load_mock_to_dw.py"
if not exist "%SCRIPT%" (
  echo ERROR: ETL script not found: %SCRIPT%>>"%LOG%"
  exit /b 1
)

set "PYTHON_EXE=%ETL_PYTHON_EXE%"
if "%PYTHON_EXE%"=="" set "PYTHON_EXE=d:\PFE_final\Python312\python.exe"

echo Using python: %PYTHON_EXE%>>"%LOG%"
"%PYTHON_EXE%" "%SCRIPT%" >>"%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo ERROR: ETL python execution failed with exit code %RC%>>"%LOG%"
  exit /b %RC%
)

echo Exit code: %RC%>>"%LOG%"
exit /b %RC%
