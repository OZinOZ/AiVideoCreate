@echo on
echo Starting Content OS Matrix Batch Processing...

:: ==============================
:: 参数读取
:: ==============================
set CONFIG=%1
set COUNT=%2

:: 如果没传数量，默认1个
if "%COUNT%"=="" set COUNT=1

echo Config: %CONFIG%
echo Total Runs: %COUNT%

pushd %~dp0
setlocal
cd /d E:\OliverAI\AiScripts\pipeline

call activate
call conda activate upwork

:: ==============================
:: 主循环
:: ==============================
set i=1

:loop
echo ==========================================
echo Running video %i% of %COUNT%
echo ==========================================

python app_channel_runner.py -c %CONFIG%

:: 如果不是最后一个，休息5分钟（300秒）
if %i% LSS %COUNT% (
    echo Waiting 5 minutes before next run...
    timeout /t 300 /nobreak
)

set /a i+=1
if %i% LEQ %COUNT% goto loop

endlocal
popd

echo ==========================================
echo All tasks finished for %CONFIG%
echo ==========================================

@echo off