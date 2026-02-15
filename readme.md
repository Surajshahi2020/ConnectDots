
<!-- Download python and git bash -->
https://www.python.org/downloads/windows/
https://git-scm.com/install/windows

<!-- Get code from this -->
git clone https://github.com/Surajshahi2020/Cyberpulse.git 

<!-- Batch file -->
@echo off
cd /d "C:\Users\user\Desktop\CyberPulse V2"

call venv\Scripts\activate.bat

REM === CONFIG ===
set HOST=0.0.0.0
set PORT=8000
REM ==============

echo Starting Django server on %HOST%:%PORT% ...
echo Opening browser to http://localhost:%PORT%/
start http://localhost:%PORT%/

python manage.py runserver 
pause