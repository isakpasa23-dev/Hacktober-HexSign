@echo off
chcp 65001 >nul
title HexSign AI Market Stok Sistemi
echo ========================================================
echo    HexSign AI Market Stok ve Kasa Kontrol Sistemi
echo ========================================================
echo.
echo Sunucu baslatiliyor...
echo Tarayicinizda http://localhost:8000 adresini acin.
echo.
"C:\Users\JET\AppData\Local\Programs\Python\Python311\python.exe" -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
