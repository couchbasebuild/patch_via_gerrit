# Testing patch_via_gerrit

These tests aim to cover at least the basic things we don't want to break.

To start, create a virtualenv somewhere (preferably outside this repository):

```shell
python3 -m venv venv
source venv/bin/activate
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

Note: the above assumes you have a `${HOME}/.ssh/patch_via_gerrit.ini` file with appropriate credentials.
If you don't, you can instead pass the credentials on the command-line like so:

```shell
PYTHONPATH=. gerrit_url=http://example.com gerrit_user=user gerrit_pass=pass pytest --cov=patch_via_gerrit -s -v
```
