@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [ERROR] .venv not found. Run setup.bat first.
    exit /b 1
)
call ".venv\Scripts\activate.bat"

set "TARGET=%~1"
if "%TARGET%"=="" set "TARGET=all"

set EXITCODE=0

if /I "%TARGET%"=="lint"        goto :lint
if /I "%TARGET%"=="typecheck"   goto :typecheck
if /I "%TARGET%"=="unit"        goto :unit
if /I "%TARGET%"=="integration" goto :integration
if /I "%TARGET%"=="coverage"    goto :coverage
if /I "%TARGET%"=="all"         goto :all

echo [ERROR] Unknown target "%TARGET%".
echo.
echo Usage: test.bat [lint^|typecheck^|unit^|integration^|coverage^|all]
echo   (no argument runs "all": lint + typecheck + unit + integration)
exit /b 1

:lint
echo ==== ruff (lint) ====
ruff check src tests
if errorlevel 1 set EXITCODE=1
goto :done

:typecheck
echo ==== mypy (type check) ====
mypy src
if errorlevel 1 set EXITCODE=1
goto :done

:unit
echo ==== pytest: unit (no browser, no network) ====
pytest tests\unit -m unit
if errorlevel 1 set EXITCODE=1
goto :done

:integration
echo ==== pytest: integration ====
echo ^(launches a real headless Chromium + a local FastAPI instance;
echo  first run downloads nothing extra, but IS slower than unit^)
pytest tests\integration -m integration
if errorlevel 1 set EXITCODE=1
goto :done

:coverage
echo ==== pytest with coverage (unit + integration) ====
coverage run -m pytest tests\unit tests\integration -q
if errorlevel 1 set EXITCODE=1
coverage report -m
goto :done

:all
echo ==== ruff (lint) ====
ruff check src tests
if errorlevel 1 set EXITCODE=1

echo.
echo ==== mypy (type check) ====
mypy src
if errorlevel 1 set EXITCODE=1

echo.
echo ==== pytest: unit ====
pytest tests\unit -m unit
if errorlevel 1 set EXITCODE=1

echo.
echo ==== pytest: integration ====
pytest tests\integration -m integration
if errorlevel 1 set EXITCODE=1

goto :done

:done
echo.
if "!EXITCODE!"=="0" (
    echo ============================================================
    echo  ALL CHECKS PASSED
    echo ============================================================
) else (
    echo ============================================================
    echo  ONE OR MORE CHECKS FAILED - scroll up for details
    echo ============================================================
)
exit /b %EXITCODE%
