@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   Window — 최초 설치 (1회만)
echo ============================================================
echo.

call "%~dp0_find_python.bat"
if errorlevel 1 goto :no_python

echo [OK] Python 확인됨
"%PY%" --version
echo     %PY%
echo.

echo 패키지 설치 중... (2~5분 소요될 수 있습니다)
"%PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo [X] pip 업그레이드 실패. 인터넷/방화벽 또는 프록시를 확인하세요.
    pause
    exit /b 1
)
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [X] 패키지 설치 실패. 인터넷 연결·회사 방화벽·프록시를 확인하세요.
    pause
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        copy /Y ".env.example" ".env" >nul
        echo.
        echo [!] .env 파일을 만들었습니다.
        echo     메모장으로 .env 를 열어 OPENAI_API_KEY= 뒤에 API 키를 붙여넣으세요.
    ) else (
        echo.
        echo [!] .env 파일이 없습니다. OPENAI_API_KEY 가 필요합니다.
    )
) else (
    echo [OK] .env 파일 있음
)

echo.
echo ============================================================
echo   설치 완료!  "실행.bat" 더블클릭
echo ============================================================
echo.
pause
exit /b 0

:no_python
echo [X] 실제 Python 이 설치되어 있지 않습니다.
echo.
echo   winget install Python.Python.3.12 --accept-package-agreements
echo.
pause
exit /b 1
