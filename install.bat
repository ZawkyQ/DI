@echo off
echo ==========================================
echo   Dynamic Island - Install Dependencies
echo ==========================================
echo.

pip install customtkinter pillow winsdk pystray vosk sounddevice pypresence numpy

echo.
echo ==========================================
echo   Done! Run "run.bat" to start the player
echo ==========================================
pause
