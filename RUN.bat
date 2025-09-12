@echo off
REM =================================================================
REM                      CAU HINH BAN DAU
REM =================================================================
REM Chuyen console sang che do UTF-8 de hien thi tieng Viet chinh xac.
chcp 65001 >nul

REM Buoc Python su dung UTF-8, giai quyet triet de loi UnicodeEncodeError.
set PYTHONUTF8=1

REM Dat tieu de cho cua so terminal.
title Image Crawler

REM Tu dong thay doi duong dan den thu muc chua file .bat nay.
REM Dieu nay giup script luon tim thay file Python mot cach chinh xac.
cd /d "%~dp0"


REM =================================================================
REM                      CAU HINH VONG LAP
REM =================================================================
set max_loops=200
set loop_count=0


:loop
set /a loop_count=loop_count+1
if %loop_count% gtr %max_loops% (
    echo.
    echo [INFO] Da dat gioi han vong lap toi da %max_loops%.
    goto end_process
)
IF EXIST stop.txt GOTO stop_process


REM =================================================================
REM                 XOAY VONG 5 FILE LOG CUOI CUNG
REM =================================================================
if exist console_run_5.log del "console_run_5.log" >nul 2>nul
if exist console_run_4.log ren "console_run_4.log" "console_run_5.log"
if exist console_run_3.log ren "console_run_3.log" "console_run_4.log"
if exist console_run_2.log ren "console_run_2.log" "console_run_3.log"
if exist console_run_1.log ren "console_run_1.log" "console_run_2.log"


REM =================================================================
REM                 BAT DAU CHAY SCRIPT VA GHI LOG
REM =================================================================
REM Dong dau tien dung > de tao file log moi cho chu ky nay.
echo ================================================================= > "console_run_1.log"
echo [%time%] Bat dau chu ky %loop_count% / %max_loops% >> "console_run_1.log"
echo ================================================================= >> "console_run_1.log"

REM Chay script Python va noi tiep output vao log. 2>&1 de bat ca thong bao loi.
python crawler\imagecrawler.py >> "console_run_1.log" 2>&1

REM Ghi thong bao ket thuc vao log.
echo. >> "console_run_1.log"
echo ----------------------------------------------------------------- >> "console_run_1.log"
echo Chu ky hoan tat. >> "console_run_1.log"
echo Lan chay tiep theo sau 5 phut (300 giay). >> "console_run_1.log"
echo ----------------------------------------------------------------- >> "console_run_1.log"


REM =================================================================
REM                    HIEN THI LOG RA MAN HINH
REM =================================================================
cls
type "console_run_1.log"


REM =================================================================
REM                TAM DUNG CO DINH 5 PHUT (300 GIAY)
REM =================================================================
timeout /t 300 /nobreak
goto loop


:stop_process
echo.
echo [!] Phat hien file "stop.txt".
del "stop.txt"
echo [!] Da xoa file "stop.txt".
goto end_process


:end_process
echo.
echo [INFO] Script da hoan tat cong viec.
pause
exit