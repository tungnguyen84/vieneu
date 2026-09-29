@echo off
title Sau Canh Cua Studio — Desktop Production Pipeline
echo ========================================================
echo   SAU CANH CUA STUDIO — DESKTOP PRODUCTION PIPELINE V1
echo ========================================================
echo Starting local production server and desktop application...
python studio\launcher.py %*
if errorlevel 1 (
    echo.
    echo Application exited with error code %errorlevel%.
    pause
)
