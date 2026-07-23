@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

call "%~dp0_find_python.bat"
if errorlevel 1 (
    echo [X] Python 없음. "사무실_최초설치.bat" 을 먼저 실행하세요.
    pause
    exit /b 1
)

echo ============================================================
echo   Window — 실행 (PC + 핸드폰)
echo ============================================================
echo.
echo [PC]       http://localhost:8502
echo.
"%PY%" -c "from network_utils import get_mobile_access_urls, is_port_listening; print('[서버]', '실행 준비' if not is_port_listening(8502) else '이미 다른 창에서 실행 중일 수 있음'); urls=get_mobile_access_urls(8502); print(''); print('[핸드폰] 아래 주소를 그대로 입력:'); print(''); [print('  >>> '+u) for u in urls]; print(''); print('※ 같은 Wi-Fi / 모바일데이터 OFF'); print('※ 안 되면: 방화벽_허용.bat (관리자)')"
echo.
echo * 이 창을 닫으면 핸드폰 접속도 끊깁니다.
echo ============================================================
echo.

start "" "http://localhost:8502"
"%PY%" -m streamlit run app.py --server.port 8502 --server.address 0.0.0.0
pause
