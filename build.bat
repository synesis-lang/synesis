@echo off
REM Quick build and validation script for Synesis (Windows)

echo ==========================================
echo Synesis Build and Validation
echo ==========================================
echo.

REM Step 1: Clean previous builds
echo [1/6] Cleaning previous builds...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist synesis.egg-info rmdir /s /q synesis.egg-info
echo [92m√ Clean complete[0m
echo.

REM Step 2: Run tests
echo [2/6] Running tests...
pytest -q
if %errorlevel% neq 0 (
    echo [91m× Tests failed. Fix errors before building.[0m
    exit /b 1
)
echo [92m√ All tests passed[0m
echo.

REM Step 3: Build package
echo [3/6] Building package...
python -m build
if %errorlevel% neq 0 (
    echo [91m× Build failed[0m
    exit /b 1
)
echo [92m√ Build successful[0m
echo.

REM Step 4: Check distribution
echo [4/6] Validating distribution with twine...
twine check dist/*
if %errorlevel% neq 0 (
    echo [91m× Distribution validation failed[0m
    exit /b 1
)
echo [92m√ Distribution valid[0m
echo.

REM Step 5: List contents
echo [5/6] Package contents:
dir dist
echo.

REM Step 6: Summary
echo [6/6] Summary
echo ----------------------------------------
echo [92m√ Package ready for publication![0m
echo.
echo Next steps:
echo   • TestPyPI: twine upload --repository testpypi dist/*
echo   • PyPI:     twine upload dist/*
echo.
echo Or run the pre-publication checklist:
echo   python check_ready.py
echo ==========================================
