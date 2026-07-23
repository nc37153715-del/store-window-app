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

echo.
echo ============================================================
echo   핸드폰 접속 주소 (Window)
echo ============================================================
echo.

"%PY%" -c "from network_utils import get_mobile_access_urls, is_port_listening; import subprocess; urls=get_mobile_access_urls(8502); print('[서버]', '실행 중 OK' if is_port_listening(8502) else '꺼짐 -> 실행.bat 먼저!'); print(''); print('핸드폰 브라우저 주소:'); [print('  >>>', u) for u in urls]; u=urls[0] if urls else ''; (subprocess.run(['clip'], input=u, text=True, check=False), print(''), print('(클립보드에 복사됨 — 메모장에 붙여넣기 가능)')) if u else None"

echo.
echo  [필수]
echo  1. Wi-Fi ON / 모바일데이터 OFF
echo  2. PC와 같은 네트워크
echo  3. 방화벽_허용.bat (관리자) — 최초 1회
echo  4. PC 실행.bat 창은 닫지 마세요
echo.
pause
