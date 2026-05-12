@echo off
setlocal

set "RRC_FOLDER=F:\GF2\xiongan\rrc"
set "REFERENCE=F:\GF2\xiongan\1\xionganS2C2348.tif"
set "OUTPUT=%RRC_FOLDER%\quality_summary.csv"

set "REFERENCE_BANDS=1,2,3,4"
set "TARGET_BANDS=1,2,3,4"
set "SCALE=10000"
set "SAMPLE_STEP=16"

python "%~dp0quality_check_rrc.py" -i "%RRC_FOLDER%" -o "%OUTPUT%" -r "%REFERENCE%" --reference-bands "%REFERENCE_BANDS%" --target-bands "%TARGET_BANDS%" --scale "%SCALE%" --sample-step "%SAMPLE_STEP%"

if errorlevel 1 pause

endlocal
