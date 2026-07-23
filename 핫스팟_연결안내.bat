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
echo   Window — 핸드폰 연결이 안 될 때 (회사망)
echo ============================================================
echo.
echo 지금 PC는 유선(회사망)만 연결되어 있습니다.
echo 회사망은 보안상 핸드폰 Wi-Fi -^> PC 접속을 막는 경우가 많습니다.
echo.
echo ------------------------------------------------------------
echo  방법 A. 방화벽 허용 (먼저 시도)
echo ------------------------------------------------------------
echo  "방화벽_허용.bat" 우클릭 ^> 관리자 권한으로 실행
echo.
echo ------------------------------------------------------------
echo  방법 B. PC 핫스팟으로 연결 (가장 확실)
echo ------------------------------------------------------------
echo  1. Windows 설정 ^> 네트워크 및 인터넷 ^> 모바일 핫스팟
echo  2. "모바일 핫스팟" 켜기
echo     (인터넷 공유 원본: 이더넷)
echo  3. 핸드폰 Wi-Fi에서 그 핫스팟에 연결
echo  4. 모바일데이터(LTE) OFF
echo  5. 아래 주소를 핸드폰 브라우저에 입력
echo.

"%PY%" -c "from network_utils import get_mobile_access_urls, is_port_listening; import subprocess; print('[서버]', '실행 중 OK' if is_port_listening(8502) else '꺼짐 -> 실행.bat 먼저!'); print(); urls=get_mobile_access_urls(8502); hotspot=[u for u in urls if u.startswith('http://192.168.137.')]; print('[추천 주소]'); (print('  >>>', hotspot[0]), subprocess.run(['clip'], input=hotspot[0], text=True, check=False), print('  (클립보드 복사됨)')) if hotspot else print('  (핫스팟을 먼저 켠 뒤 이 파일을 다시 실행하세요)'); print(); print('[현재 PC에서 보이는 모든 주소]'); [print(' ', u) for u in urls] if urls else print('  (없음)')"

echo.
echo  ※ 핫스팟을 켠 뒤 IP는 보통 http://192.168.137.1:8502 입니다.
echo  ※ 실행.bat 검은 창은 계속 켜 두세요.
echo.
pause
