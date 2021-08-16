set START_DIR="%CD%"

set SCRIPTPATH=%~dp0

echo Setting up Python virtual environment
if not exist "build\" (
    mkdir build
)
python3 -m venv build/venv || goto error
call .\build\venv\Scripts\activate.bat || goto error

echo Adding pyinstaller
pip3 install pyinstaller==4.2 || goto error

echo Installing certifi
pip3 install certifi || goto error

echo Installing patch_via_gerrit requirements
pip3 install -r "%SCRIPTPATH%\requirements.txt" || goto error

echo Compiling patch_via_gerrit
set PYINSTDIR=build\pyinstaller
if not exist "%PYINSTDIR%\" (
    mkdir %PYINSTDIR%
)
pyinstaller --workpath %PYINSTDIR% ^
    --specpath %PYINSTDIR% ^
    --distpath dist --noconfirm ^
    --onefile ^
    --paths "%SCRIPTPATH%\patch_via_gerrit\scripts" ^
    "%SCRIPTPATH%\patch_via_gerrit\scripts\patch_via_gerrit.py" || goto error

goto eof

:error
set CODE=%ERRORLEVEL%
cd "%START_DIR%"
echo "Failed with error code %CODE%"
exit /b %CODE%

:eof
cd "%START_DIR%"
