@echo off
setlocal

:: Set the number of loops and delay in seconds
set "MAX_LOOPS=10"
set "DELAY_SECONDS=1800"

:: Set the path to the Python executable and your script
set "PYTHON_EXE=C:\Python39\python.exe"
set "SCRIPT_PATH=D:\imagecrawler\main.py"

:: Get the current date and time to create a unique log file name
for /f "tokens=2-4 delims=/ " %%a in ('date /t') do (set mydate=%%c-%%a-%%b)
for /f "tokens=1-2 delims=:" %%a in ('time /t') do (set mytime=%%a-%%b)
set "LOG_FILE=%mydate%_%mytime%.log"

echo Starting automated image crawler at %date% %time% >> %LOG_FILE%
echo --- >> %LOG_FILE%

:: Loop to run the script
for /l %%i in (1, 1, %MAX_LOOPS%) do (
    echo. >> %LOG_FILE%
    echo Loop %%i of %MAX_LOOPS% started at %date% %time% >> %LOG_FILE%
    echo Running script... >> %LOG_FILE%
    
    :: Run the Python script and redirect its output to the log file
    "%PYTHON_EXE%" "%SCRIPT_PATH%" >> %LOG_FILE% 2>&1
    
    echo Loop %%i finished. >> %LOG_FILE%

    :: Pause for the specified delay, unless it's the last loop
    if %%i lss %MAX_LOOPS% (
        echo Waiting %DELAY_SECONDS% seconds for the next run... >> %LOG_FILE%
        timeout /t %DELAY_SECONDS% /nobreak
    )
)

echo. >> %LOG_FILE%
echo All loops completed. Exiting. >> %LOG_FILE%
echo.

endlocal