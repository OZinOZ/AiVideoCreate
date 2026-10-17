@echo on
echo Starting Content OS Matrix Batch Processing...

:: ==============================
:: 参数读取
:: ==============================
set CONFIG=%1

echo Config: %CONFIG%

pushd %~dp0
setlocal
cd /d E:\OliverAI\AiScripts\pipiline_local

call activate
call conda activate upwork

:: ==============================
:: 主循环
:: ==============================

:loop
echo ==========================================
echo Running video %CONFIG% with idle monitor
echo ==========================================

python idle_monitor.py -c %CONFIG%

endlocal
popd

echo ==========================================
echo All tasks finished for %CONFIG%
echo ==========================================

@echo off