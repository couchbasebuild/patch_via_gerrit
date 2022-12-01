# Testing patch_via_gerrit

These tests aim to cover at least the basic things we don't want to break.

To start, create a virtualenv somewhere (preferably outside this repository):

```shell
python3 -m venv /tmp/venv
source /tmp/venv/bin/activate
```

cd into the top level directory of this repository.

Install package requirements, pytest and pytest-cov:

```shell
pip3 install -r requirements.txt
pip3 install pytest pytest-cov
```

Run the tests:

```shell
PYTHONPATH=. pytest --cov=patch_via_gerrit -s -v
```

If you only want to run a subset of tests (say you're developing a new test),
you can also pass `-k expression` to specify a python-like expression of
substrings to match. For example,

```shell
PYTHONPATH=. pytest --cov=patch_via_gerrit -s -v -k 'patch_repo_sync and not mad_hatter'
```

will run all tests that patch a repo sync, except those that deal with
mad-hatter.

Note: the above assumes you have a `${HOME}/.ssh/patch_via_gerrit.ini` file with appropriate credentials.
If you don't, you can instead pass the credentials on the command-line like so:

```shell
PYTHONPATH=. gerrit_url=https://example.com gerrit_user=user gerrit_pass=pass pytest --cov=patch_via_gerrit -s -v
```
