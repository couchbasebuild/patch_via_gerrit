import os
from subprocess import Popen, PIPE
from tempfile import TemporaryDirectory

_temp_dir = None
source_path = ""

def reset_checkout():
    global _temp_dir, source_path
    if _temp_dir is None:
        _temp_dir = TemporaryDirectory()
        source_path = _temp_dir.name

    process = Popen([
        'repo', 'init',
        '-u', 'git://github.com/couchbase/manifest',
        '-m', 'python_tools/patch_via_gerrit/testsuite.xml'
    ], stdout=PIPE, stderr=PIPE, cwd=source_path)
    stdout, stderr = process.communicate()

    # Clean up any stale manifest changes
    process = Popen([
        'git', 'reset', '--hard', 'origin/master'
    ], stdout=PIPE, stderr=PIPE, cwd=os.path.join(source_path, '.repo', 'manifests'))
    stdout, stderr = process.communicate()

    process = Popen([
        'repo', 'sync', '-j4'
    ], stdout=PIPE, stderr=PIPE, cwd=source_path)
    stdout, stderr = process.communicate()
