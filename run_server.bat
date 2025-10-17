@echo off
cd /d %~dp0
REM Ensure required env vars are set in system, or uncomment and set below (not recommended for secrets)
REM set "ab-cd1234efgh5678ijkl90mnopqrstuvwx "
REM Start the app using the bundled python
.\python\python.exe run_server.py
