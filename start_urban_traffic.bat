@echo off
set "PROJECT=%~dp0"

start "Urban Traffic Backend" powershell -NoExit -Command "Set-Location -LiteralPath '%PROJECT%'; & '.\.venv\Scripts\python.exe' -m uvicorn app.main:app --app-dir Backend --reload --host 127.0.0.1 --port 8000"

timeout /t 3 /nobreak >nul

start "Urban Traffic Frontend" powershell -NoExit -Command "$env:API_BASE_URL='http://localhost:8000/api'; Set-Location -LiteralPath '%PROJECT%Frontend'; & '..\.venv\Scripts\python.exe' -m streamlit run app.py"