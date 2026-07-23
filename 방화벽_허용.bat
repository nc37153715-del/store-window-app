@echo off
chcp 65001 >nul
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
    echo ============================================================
    echo   [필수] 관리자 권한으로 다시 실행해 주세요
    echo ============================================================
    echo.
    echo 1. 이 파일(방화벽_허용.bat)을 우클릭
    echo 2. "관리자 권한으로 실행" 선택
    echo 3. UAC 창에서 "예" 클릭
    echo.
    echo 방화벽이 막혀 있으면 핸드폰에서 접속이 안 됩니다.
    echo.
    pause
    exit /b 1
)

echo Streamlit 포트 8502 방화벽 허용 규칙 추가 중...
netsh advfirewall firewall delete rule name="Window App 8502" >nul 2>&1
netsh advfirewall firewall add rule name="Window App 8502" dir=in action=allow protocol=TCP localport=8502 profile=any
if errorlevel 1 (
    echo 규칙 추가에 실패했습니다.
    pause
    exit /b 1
)

echo.
echo [완료] 포트 8502 인바운드 허용됨
echo.
echo 다음 단계:
echo  1. 실행.bat 이 켜져 있는지 확인
echo  2. 회사 Wi-Fi로 안 되면 "핫스팟_연결안내.bat" 실행
echo.
pause
