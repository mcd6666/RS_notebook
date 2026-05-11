@echo off

setlocal



set "PYTHON=python"



set "IN_FOLDER=F:\GF2\xiongan\rh"

set "GEOM_FOLDER=F:\GF2\xiongan\jh"

set "RRC_FOLDER=F:\GF2\xiongan\rrc1"

set "REFERENCE=F:\GF2\xiongan\1\xionganS2C2348.tif"

set "DEM=F:\auxilary_data\china_dem_30m.tif"



set "SATELLITE_GEOM=C:\satgeom\v0.1\satellite-geom.exe"

set "BA=C:\satgeom\v0.1\ba.exe"



set "PRJ=ref"

set "REFERENCE_BANDS=1,2,3,4"

set "TARGET_BANDS=1,2,3,4"

set "SCALE=10000"
set "SAMPLE_STEP=4"
set "PIF_METHOD=imad"

set "IMAD_ITER=100"

set "IMAD_DELTA=0.001"
set "PIF_NCP_THRESH=0.95"

set "REGRESSION_METHOD=orthogonal"
set "ROI_TILE_SIZE=512"
set "ROI_TOP_PERCENT=20"

set "ROI_MAX_TILES=20"



set "EXTRA_FLAGS=--skip-geometry --overwrite-rrc"



set "PRJ_ARGS="

if not "%PRJ%"=="" set "PRJ_ARGS=-p %PRJ%"



echo Running command:

echo "%PYTHON%" "%~dp0run_gf_preprocess.py" -i "%IN_FOLDER%" -g "%GEOM_FOLDER%" -o "%RRC_FOLDER%" -r "%REFERENCE%" -d "%DEM%" %PRJ_ARGS% --satellite-geom "%SATELLITE_GEOM%" --ba "%BA%" --reference-bands "%REFERENCE_BANDS%" --target-bands "%TARGET_BANDS%" --scale "%SCALE%" --sample-step "%SAMPLE_STEP%" --pif-method "%PIF_METHOD%" --imad-iter "%IMAD_ITER%" --imad-delta "%IMAD_DELTA%" --pif-ncp-thresh "%PIF_NCP_THRESH%" --regression-method "%REGRESSION_METHOD%" --roi-tile-size "%ROI_TILE_SIZE%" --roi-top-percent "%ROI_TOP_PERCENT%" --roi-max-tiles "%ROI_MAX_TILES%" %EXTRA_FLAGS%

echo.



"%PYTHON%" "%~dp0run_gf_preprocess.py" -i "%IN_FOLDER%" -g "%GEOM_FOLDER%" -o "%RRC_FOLDER%" -r "%REFERENCE%" -d "%DEM%" %PRJ_ARGS% --satellite-geom "%SATELLITE_GEOM%" --ba "%BA%" --reference-bands "%REFERENCE_BANDS%" --target-bands "%TARGET_BANDS%" --scale "%SCALE%" --sample-step "%SAMPLE_STEP%"  --pif-method "%PIF_METHOD%" --imad-iter "%IMAD_ITER%" --imad-delta "%IMAD_DELTA%" --pif-ncp-thresh "%PIF_NCP_THRESH%" --regression-method "%REGRESSION_METHOD%" --roi-tile-size "%ROI_TILE_SIZE%" --roi-top-percent "%ROI_TOP_PERCENT%" --roi-max-tiles "%ROI_MAX_TILES%" %EXTRA_FLAGS%




echo.
if errorlevel 1 (

  echo Failed.

) else (

  echo Finished.

)


pause



endlocal