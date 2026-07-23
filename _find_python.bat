@echo off
REM Shared helper: sets PY to a real python.exe (not Windows Store stub).
REM Call with: call "%~dp0_find_python.bat"
REM On success: errorlevel 0 and PY is set. On failure: errorlevel 1.

set "PY="

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PY=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PY=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python313\python.exe" set "PY=%LocalAppData%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LocalAppData%\Programs\Python\Python314\python.exe" set "PY=%LocalAppData%\Programs\Python\Python314\python.exe"

if not defined PY (
  where py >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%I"
  )
)

if not defined PY (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('where python') do (
      echo %%I | findstr /I "\\WindowsApps\\" >nul
      if errorlevel 1 (
        if not defined PY set "PY=%%I"
      )
    )
  )
)

if not defined PY exit /b 1

for %%A in ("%PY%") do if %%~zA LSS 1024 exit /b 1

"%PY%" -c "import sys" >nul 2>&1
if errorlevel 1 exit /b 1

exit /b 0
