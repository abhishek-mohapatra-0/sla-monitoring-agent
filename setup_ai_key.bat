@echo off
REM Opens app\.env so you can paste a FREE LLM key (Groq / Gemini) and optional e-mail settings.
cd /d "%~dp0app"
if not exist ".env" copy ".env.example" ".env" >nul
echo.
echo  1. A browser tab opens on the Groq console - sign in and click "Create API Key" (free).
echo  2. Notepad opens app\.env - paste the key after LLM_API_KEY= and save (Ctrl+S).
echo  3. Restart run_dashboard.bat. The AI Agent tab then shows "groq" instead of "offline".
echo.
start "" "https://console.groq.com/keys"
start "" notepad ".env"
pause
