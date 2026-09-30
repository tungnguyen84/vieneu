@echo off
title Sau Canh Cua Studio — Desktop Production Pipeline
echo ========================================================
echo   SAU CANH CUA STUDIO — DESKTOP PRODUCTION PIPELINE V1
echo ========================================================
set PYTHON_EXE=python
if exist ".venv\Scripts\python.exe" (
    set PYTHON_EXE=.venv\Scripts\python.exe
)
echo Starting local production server and desktop application using %PYTHON_EXE%...
%PYTHON_EXE% studio\launcher.py %*
if errorlevel 1 (
    echo.
    echo Application exited with error code %errorlevel%.
    pause
)
