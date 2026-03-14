@echo off
setlocal
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
echo OK: Clean complete
echo.

REM Step 2: Run tests
echo [2/6] Running tests...
python -m pytest -q
if errorlevel 1 (
    echo ERROR: Tests failed. Fix errors before building.
    exit /b 1
)
echo OK: All tests passed
echo.

REM Step 3: Build package
echo [3/6] Building package...
python -m build
if errorlevel 1 (
    echo ERROR: Build failed
    exit /b 1
)
echo OK: Build successful
echo.

REM Step 4: Check distribution
echo [4/6] Validating distribution with twine...
python -m twine check dist/*
if errorlevel 1 (
    echo ERROR: Distribution validation failed
    exit /b 1
)
echo OK: Distribution valid
echo.

REM Step 5: List contents
echo [5/6] Package contents:
dir dist
echo.

REM Step 6: Summary
echo [6/6] Summary
echo ----------------------------------------
echo OK: Package ready for publication!
echo.
echo Next steps:
echo   TestPyPI: python -m twine upload --repository testpypi dist/*
echo   PyPI:     python -m twine upload dist/*
echo.
echo Or run the pre-publication checklist:
echo   python check_ready.py
echo ==========================================
endlocal
