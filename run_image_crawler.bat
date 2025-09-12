@echo off
setlocal enabledelayedexpansion

title Image Crawler
cd /d "%~dp0"
set "PYTHONIOENCODING=utf-8"

REM =================================================================
REM                  CẤU HÌNH CRAWLER
REM =================================================================
set "MAX_LOOPS=200"
set "DELAY_SECONDS=10"
set "MAX_LOGS=5"

REM =================================================================
REM                  VÒNG LẶP CHÍNH
REM =================================================================
for /l %%i in (1,1,%MAX_LOOPS%) do (
    REM Xoay vòng log
    if exist console_run_%MAX_LOGS%.log del console_run_%MAX_LOGS%.log
    for /l %%j in (%MAX_LOGS%,-1,2) do (
        if exist console_run_%%j-1.log ren console_run_%%j-1.log console_run_%%j.log
    )
    set "CUR_LOG=console_run_1.log"

    REM Header
    echo [!time!] Starting cycle %%i of %MAX_LOOPS% | powershell -Command "param($f); tee -FilePath $f -Append" -f "!CUR_LOG!"
    echo ================================================================= | powershell -Command "param($f); tee -FilePath $f -Append" -f "!CUR_LOG!"

    REM Chạy Python, log y hệt console
    python crawler\imagecrawler.py 2>&1 | powershell -Command "param($f); tee -FilePath $f -Append" -f "!CUR_LOG!"

    REM Footer
    echo. | powershell -Command "param($f); tee -FilePath $f -Append" -f "!CUR_LOG!"
    echo ----------------------------------------------------------------- | powershell -Command "param($f); tee -FilePath $f -Append" -f "!CUR_LOG!"
    echo Crawl cycle finished. Output saved to !CUR_LOG! | powershell -Command "param($f); tee -FilePath $f -Append" -f "!CUR_LOG!"

    if %%i lss %MAX_LOOPS% (
        echo Next run will be in %DELAY_SECONDS% seconds. | powershell -Command "param($f); tee -FilePath $f -Append" -f "!CUR_LOG!"
        echo ----------------------------------------------------------------- | powershell -Command "param($f); tee -FilePath $f -Append" -f "!CUR_LOG!"
    ) else (
        echo All cycles completed. Exiting. | powershell -Command "param($f); tee -FilePath $f -Append" -f "!CUR_LOG!"
    )

    if %%i lss %MAX_LOOPS% (
        echo. 
        echo Waiting for %DELAY_SECONDS% seconds, press CTRL+C to quit ...
        ping -n %DELAY_SECONDS% localhost >nul
    )
)

endlocal
