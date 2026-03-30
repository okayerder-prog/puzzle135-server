@echo off
chcp 65001 >nul 2>&1
title PUZZLE135 - GPU Worker Kurulum
color 0A

echo.
echo ═══════════════════════════════════════════════════════════
echo    PUZZLE135 - GPU Worker (Vulkan/DX12 - Tum GPU'lar)
echo    AMD / NVIDIA / Intel - CUDA gerekmez!
echo ═══════════════════════════════════════════════════════════
echo.

:: Zaten kurulu mu?
where kangaroo >nul 2>&1
if %errorlevel% == 0 (
    echo [OK] Kangaroo zaten kurulu!
    goto RUN
)

echo [1/3] Rust kuruluyor (GPU worker icin gerekli)...
echo       Bu islem yaklasik 3-5 dakika surer, bir kez yapilir.
echo.

:: Rust indir ve kur
curl -L -o "%TEMP%\rustup-init.exe" "https://win.rustup.rs/x86_64"
if %errorlevel% neq 0 (
    echo [HATA] Rust indirilemedi. Internet baglantisini kontrol et.
    pause
    exit /b 1
)

"%TEMP%\rustup-init.exe" -y --default-toolchain stable --profile minimal
del "%TEMP%\rustup-init.exe" >nul 2>&1

:: PATH yenile
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

echo.
echo [2/3] Kangaroo GPU kuruluyor...
echo       (Vulkan/DX12 destekli, tum GPU'larla calısır)
echo.

call "%USERPROFILE%\.cargo\bin\cargo.exe" install kangaroo

if %errorlevel% neq 0 (
    echo [HATA] Kangaroo kurulamadi.
    echo        Visual C++ Build Tools gerekebilir:
    echo        https://visualstudio.microsoft.com/visual-cpp-build-tools/
    pause
    exit /b 1
)

echo.
echo [OK] Kurulum tamamlandi!
echo.

:RUN
:: Python var mi?
python --version >nul 2>&1
if %errorlevel% == 0 (set PY=python & goto START_WORKER)
py --version >nul 2>&1
if %errorlevel% == 0 (set PY=py & goto START_WORKER)

echo [3/3] Python kuruluyor...
curl -L -o "%TEMP%\pysetup.exe" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
"%TEMP%\pysetup.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
del "%TEMP%\pysetup.exe" >nul 2>&1
set PY=python

:START_WORKER
echo [3/3] Worker baslatiliyor...
echo.

:: Worker indir
if not exist "worker.py" (
    curl -L -o "worker.py" "https://puzzle135-server-production.up.railway.app/api/download/worker?wax=__WAX__&type=vulkan"
)

:: Worker'a kangaroo yolunu bildir
set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"

%PY% worker.py

pause
