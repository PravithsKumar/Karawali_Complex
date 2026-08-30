@echo off
title Karavali Complex - Rent Management System
echo ========================================================
echo Starting Karavali Complex Rent Tracker...
echo ========================================================
echo.

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate
    pip install -r requirements.txt
    python seed.py
) else (
    call venv\Scripts\activate
)

echo Starting Flask Application...
echo Open your browser at: http://127.0.0.1:5000
echo.
python app.py
pause
