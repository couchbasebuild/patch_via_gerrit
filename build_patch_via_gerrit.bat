setlocal EnableDelayedExpansion
@echo on

set START_DIR="%CD%"
set SCRIPTDIR=%~dp0
rem Get directory containing script without trailing \
set SCRIPTPATH=%SCRIPTDIR:~0,-1%

echo Setting up Python virtual environment
if not exist "build\" (
    mkdir build
)
python3 -m venv build/venv || goto error
call .\build\venv\Scripts\activate.bat || goto error

echo Adding pyinstaller
pip3 install PyInstaller==4.10 || goto error
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
    set PYINSTPATHS=%VERSIONPATH%;%SCRIPTPATH%
    echo __version__ = "%VERSION%" > %VERSIONPATH%\_buildversion.py
    echo __build__ = "%BLD_NUM%" >> %VERSIONPATH%\_buildversion.py
) else (
    set PYINSTPATHS=%SCRIPTPATH%
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
    --name patch_via_gerrit ^
    "%SCRIPTPATH%\patch_via_gerrit\scripts\main.py" || goto error

goto eof

:error
set CODE=%ERRORLEVEL%
cd "%START_DIR%"
echo "Failed with error code %CODE%"
exit /b %CODE%

:eof
cd "%START_DIR%"
