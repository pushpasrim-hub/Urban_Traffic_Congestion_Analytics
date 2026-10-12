@echo off
set "PROJECT=%~dp0"

start "Urban Traffic Backend" powershell -NoExit -Command "Set-Location -LiteralPath '%PROJECT%Backend'; & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001"

timeout /t 3 /nobreak >nul

start "Urban Traffic Frontend" powershell -NoExit -Command "$env:API_BASE_URL='http://127.0.0.1:8001/api'; Set-Location -LiteralPath '%PROJECT%Frontend'; & '.\.venv\Scripts\python.exe' -m streamlit run app.py"