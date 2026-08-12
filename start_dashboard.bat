@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
  echo Creating Python 3.12 virtual environment...
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Failed to create venv. Install Python 3.12 from python.org first.
    pause
    exit /b 1
  )
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Starting CPR Swing Scanner dashboard...
echo Browser should open at http://localhost:8501
echo Press Ctrl+C to stop.
echo.
streamlit run dashboard.py

pause
