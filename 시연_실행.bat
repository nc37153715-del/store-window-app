@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".env" (
    echo [X] .env 파일이 없습니다. API 키 설정 후 다시 실행하세요.
    pause
    exit /b 1
)

call "%~dp0_find_python.bat"
if errorlevel 1 (
    echo [X] Python 없음. "사무실_최초설치.bat" 을 먼저 실행하세요.
    pause
    exit /b 1
)

echo ============================================================
echo   Window — 시연 실행
echo ============================================================
echo.

echo [1] PC 브라우저: http://localhost:8502
echo.
"%PY%" -c "from network_utils import get_mobile_access_urls, is_port_listening; urls=get_mobile_access_urls(8502); print('[2] 핸드폰 시연 주소:'); [print('    '+u) for u in urls]; print(''); print('[3] 서버', '이미 실행 중' if is_port_listening(8502) else '시작합니다...')"
echo.
echo * 이 창을 닫으면 프로그램이 종료됩니다.
echo ============================================================
echo.

start "" "http://localhost:8502"
"%PY%" -m streamlit run app.py --server.port 8502 --server.address 0.0.0.0
pause
