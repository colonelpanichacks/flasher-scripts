@echo off
:: ESP32 Firmware Flasher Menu - Windows
:: Just run this file to start

title ESP32 Firmware Flasher

cd /d "%~dp0"

where python >nul 2>&1 && (python flash.py & goto :end)
where python3 >nul 2>&1 && (python3 flash.py & goto :end)
where py >nul 2>&1 && (py -3 flash.py & goto :end)

echo.
echo ERROR: Python not found!
echo Install from: https://www.python.org/downloads/
echo.
pause

:end
