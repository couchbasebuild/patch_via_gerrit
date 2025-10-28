# patch_via_gerrit wrapper scripts

`patch_via_gerrit` is deployed using `uv`. While it can be installed
this way on an agent, many CI jobs download the executable directly from
a central location rather than expecting it on `$PATH`.

To support this use case, this directory contains a shell script (for Linux
and MacOS) and a Go program (for Windows) that can be downloaded and run
directly. This approach follows the same methodology as the `cbdep` package.

Both implementations follow the same general algorithm:

    add `$HOME/.local/bin` to PATH
    if `$HOME/.local/bin/patch_via_gerrit` does not exist:
        if `$HOME/.local/bin/uv` does not exist:
            install uv using downloaded installation script
        run `uv tool install patch_via_gerrit`
    elif `$HOME/.local/bin/patch_via_gerrit` is more than a couple days old:
        run `uv tool install --reinstall patch_via_gerrit`
    run `$HOME/.local/bin/patch_via_gerrit` passing through all arguments

This ensures the wrapper automatically picks up new released versions
of patch_via_gerrit.

## Installing uv

The `uv` binary is a single file with no dependencies. Rather than downloading
it directly, these wrappers use the official `curl | sh` installer script,
which automatically handles platform detection, architecture selection, and
version management.

The installer places `uv` into `$HOME/.local/bin` on all platforms (or
`%USERPROFILE%\.local\bin` on Windows). The `uv tool install` command
creates the `patch_via_gerrit` binary in the same location.

## Windows

On Linux/Mac, the above logic is implemented as a shell script. On Windows,
a Go program is used instead to produce a native `.exe` file.

The Windows implementation handles several platform-specific considerations:

- The download must be named `patch_via_gerrit.exe` and be a native executable,
  ruling out `.bat` or `.ps1` scripts
- The `patch_via_gerrit.exe` created by `uv` in `%USERPROFILE%\.local\bin` is
  not modified by `uv tool install --reinstall`, so the wrapper deletes it
  before reinstalling when an update is needed
- The recommended Powershell installer for `uv` fails with SSL errors on some
  Windows systems. The Go program works around this by explicitly enabling
  TLS1.2 when invoking `powershell`

## Releasing wrapper scripts

`release-wrappers.sh` is a convenience script to upload the wrapper
script/program to all the historical filenames on S3. Ideally, this
should only need to be run once, as these same wrappers should work
indefinitely. However, the script can be re-run if updates are needed.
