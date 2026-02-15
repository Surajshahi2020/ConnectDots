@echo off
cd /d "C:\Users\cyber\Desktop\CyberPulse V2"

call venv\Scripts\activate.bat

REM === CONFIG ===
set HOST=0.0.0.0
set PORT=8000
REM ==============

echo Starting Django server on %HOST%:%PORT% ...
echo Opening browser to http://localhost:%PORT%/
start http://localhost:%PORT%/

uvicorn threatwatch.asgi:application --host %HOST% --port %PORT% --reload

pause
