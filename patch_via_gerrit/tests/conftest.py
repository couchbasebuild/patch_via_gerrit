import os
from subprocess import Popen, PIPE
from tempfile import TemporaryDirectory
from pathlib import Path

_temp_dir = TemporaryDirectory()
source_path = _temp_dir.name

# Get the path to the repo root, relative to this file
repo_root = Path(__file__).parent.parent.parent.resolve()

def reset_checkout():
    process = Popen([
        'repo', 'init',
        '-u', f'file://{repo_root}',
        '-m', 'patch_via_gerrit/tests/manifest.xml'
    ], stdout=PIPE, stderr=PIPE, cwd=source_path)
    stdout, stderr = process.communicate()

    # Clean up any stale manifest changes
    process = Popen([
        'git', 'reset', '--hard', 'HEAD'
    ], stdout=PIPE, stderr=PIPE, cwd=os.path.join(source_path, '.repo', 'manifests'))
    stdout, stderr = process.communicate()

    process = Popen([
        'repo', 'sync', '-j4'
    ], stdout=PIPE, stderr=PIPE, cwd=source_path)
    stdout, stderr = process.communicate()
    os.chdir(source_path)
