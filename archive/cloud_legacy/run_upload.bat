@echo on
echo Starting Content OS Matrix Batch Processing...

:: ==============================
:: 参数读取
:: ==============================
set CONFIG=%1
set LANG=%2

if "%LANG%"=="" set LANG=en

echo Config: %CONFIG%
echo Language: %LANG%

pushd %~dp0
setlocal
cd /d E:\OliverAI\AiScripts\pipeline

call activate
call conda activate upwork

python youtube_uploader.py %CONFIG% %LANG%

endlocal
popd

echo ==========================================
echo All tasks finished for %CONFIG%
echo ==========================================

@echo off