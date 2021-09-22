setlocal EnableDelayedExpansion
@echo on

set START_DIR="%CD%"
set SCRIPTPATH=%~dp0

echo Setting up Python virtual environment
if not exist "build\" (
    mkdir build
)
python3 -m venv build/venv || goto error
call .\build\venv\Scripts\activate.bat || goto error

echo Adding pyinstaller
pip3 install pyinstaller==4.5.1 || goto error
echo Installing certifi
pip3 install certifi || goto error

echo Installing patch_via_gerrit requirements
pip3 install -r "%SCRIPTPATH%\requirements.txt" || goto error

@echo on

rem Customize _buildversion.py if build info available in environment
set VERSIONPATH=build\version
rmdir /s /q %VERSIONPATH%
mkdir %VERSIONPATH%

if not "%VERSION%" == "" (
    set PYINSTPATHS=%VERSIONPATH%;%SCRIPTPATH%\patch_via_gerrit\scripts
    echo __version__ = "%VERSION%" > %VERSIONPATH%\_buildversion.py
    echo __build__ = "%BLD_NUM%" >> %VERSIONPATH%\_buildversion.py
) else (
    set PYINSTPATHS=%SCRIPTPATH%\patch_via_gerrit\scripts
)

echo Compiling patch_via_gerrit
set PYINSTDIR=build\pyinstaller
if not exist "%PYINSTDIR%\" (
    mkdir %PYINSTDIR%
)
pyinstaller --workpath %PYINSTDIR% ^
    --specpath %PYINSTDIR% ^
    --distpath dist --noconfirm ^
    --onefile ^
    --paths "%PYINSTPATHS%" ^
    "%SCRIPTPATH%\patch_via_gerrit\scripts\patch_via_gerrit.py" || goto error

goto eof

:error
set CODE=%ERRORLEVEL%
cd "%START_DIR%"
echo "Failed with error code %CODE%"
exit /b %CODE%

:eof
cd "%START_DIR%"
