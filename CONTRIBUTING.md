# Contributing to patch_via_gerrit

## Development Setup

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

To set up your development environment:

1. Install `uv` if you don't have it:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Clone the repository and navigate to the project directory

3. Install development dependencies:
   ```bash
   uv sync
   ```

## Project Structure

```
patch_via_gerrit/
├── patch_via_gerrit/       # Main package source
│   ├── scripts/
│   │   └── main.py         # Main application logic
│   └── tests/              # Test suite
│       ├── conftest.py     # Test fixtures
│       └── test_patch_via_gerrit.py
├── wrapper/                # Wrapper scripts for direct download
├── pyproject.toml          # Project metadata and dependencies
├── requirements.txt        # Pinned dependencies (for reference)
└── README.md               # User-facing documentation
```

## Running the Tool During Development

To run `patch_via_gerrit` from source without installing:

```bash
uv run patch_via_gerrit --help
```

Or activate the virtual environment:

```bash
source .venv/bin/activate  # On Linux/macOS
# or
.venv\Scripts\activate     # On Windows

patch_via_gerrit --help
```

## Running Tests

The test suite includes integration tests that interact with a real Gerrit instance.

### Prerequisites for Testing

Tests require Gerrit credentials. The test suite will look for credentials in one of two ways:

**Option 1: Configuration file** (recommended)

Create `~/.ssh/patch_via_gerrit.ini`:
```ini
[main]
gerrit_url = http://review.couchbase.org
username = your_username
password = your_http_password
```

**Option 2: Environment variables** (for CI/automated testing)

If the config file doesn't exist, the tests will fall back to environment variables:
```bash
export gerrit_url=http://review.couchbase.org
export gerrit_user=your_username
export gerrit_pass=your_http_password
```

**Note:** The main `patch_via_gerrit` tool itself only supports the config file. Environment variables are only available in the test suite.

### Running Tests

To run the full test suite:

```bash
uv run pytest
```

Run specific test files:

```bash
uv run pytest patch_via_gerrit/tests/test_patch_via_gerrit.py
```

Run specific tests:

```bash
uv run pytest patch_via_gerrit/tests/test_patch_via_gerrit.py::test_cd
```

Run with verbose output:

```bash
uv run pytest -v
```

### Test Coverage

The test suite includes:

- Unit tests for utility functions (`test_cd()`)
- Integration tests for Gerrit API interactions
- Tests for review dependency resolution
- Tests for branch filtering and manifest handling
- Tests for edge cases (missing directories, closed reviews, etc.)

**Note:** Integration tests use real review IDs from the Couchbase Gerrit instance. Some tests may fail if those reviews are deleted or if you don't have access to them.


## Making Changes

1. Create a new branch for your changes
2. Make your changes and add/update tests as needed
3. Run the test suite to ensure everything passes
4. Update documentation if you've changed functionality
5. Commit your changes with clear, descriptive commit messages

## Publishing

This project uses [flit](https://flit.pypa.io/) as its build system for ease of publishing.

### Prerequisites

Publishing requires credentials configured in `~/.pypirc`. The project is published as `patch-via-gerrit` on PyPI (note the hyphen, not underscore). See the [flit documentation](https://flit.pypa.io/en/stable/upload.html) for details on configuration.

Example `~/.pypirc`:

```ini
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-...

[testpypi]
repository = https://test.pypi.org/legacy/
username = __token__
password = pypi-...
```


### Publishing to TestPyPI

It's recommended to first publish to TestPyPI to verify everything works:

```bash
uv run flit publish --repository testpypi
```

Then test the installation:

```bash
uv tool install --extra-index-url https://test.pypi.org/simple/ --index-strategy unsafe-best-match patch-via-gerrit
```

**Notes:**
- Use `--extra-index-url` (not `--index-url`) so that dependencies can still be resolved from the main PyPI while the `patch-via-gerrit` package itself comes from TestPyPI.
- The `--index-strategy unsafe-best-match` flag allows `uv` to find the best matching versions across all indexes, since TestPyPI doesn't have all dependency versions.

### Publishing to PyPI

Once verified, publish to the main PyPI repository:

```bash
uv run flit publish
```

Users can then install the new version:

```bash
uv tool install patch-via-gerrit
# or update existing installation
uv tool install --reinstall patch-via-gerrit
```

### Publishing Wrapper Scripts

The wrapper scripts in the `wrapper/` directory allow users to download and run `patch_via_gerrit` without pre-installation. See [wrapper/README.md](wrapper/README.md) for details on how these work.

If you need to update the wrapper scripts and republish them:

```bash
cd wrapper
./release-wrappers.sh
```

This uploads the wrapper scripts to S3 at `packages.couchbase.com`. You'll need appropriate AWS credentials configured.

## Dependency Management

### Adding Dependencies

To add a new runtime dependency:

```bash
uv add <package-name>
```

To add a development dependency:

```bash
uv add --dev <package-name>
```

This will update both `pyproject.toml` and `uv.lock`.

### Updating Dependencies

To update all dependencies to their latest compatible versions:

```bash
uv lock --upgrade
```

To update a specific package:

```bash
uv lock --upgrade-package <package-name>
```

### Syncing Environment

After pulling changes that modified dependencies:

```bash
uv sync
```

## Debugging

### Verbose Logging

The tool includes extensive debug logging. When developing or troubleshooting:

```bash
uv run patch_via_gerrit -d -r 134808
```

This will show:
- Gerrit API queries being made
- Review IDs found at each step
- Dependency resolution process
- Manifest parsing details
- Git commands being executed

### Interactive Debugging

You can use Python's debugger while developing:

```python
import pdb; pdb.set_trace()
```

Or use your IDE's debugging features with `uv run` as the command.

## Common Development Tasks

**Run tests:**
```bash
uv run pytest
```

**Run with coverage:**
```bash
uv run pytest --cov=patch_via_gerrit --cov-report=html
```

**Check version:**
```bash
uv run patch_via_gerrit --version
```

**Test the CLI directly:**
```bash
uv run patch_via_gerrit --version
```

## Getting Help

If you encounter issues or have questions:

1. Check the [README.md](README.md) for usage information
2. Look at existing tests for examples of how things work
3. Run with `--debug` to see detailed execution information
4. Review the code in `patch_via_gerrit/scripts/main.py` - it's well-commented

## Wrapper Scripts

The `wrapper/` directory contains scripts that can be downloaded and run directly without pre-installing `patch_via_gerrit`. These are primarily for CI/CD environments.

See [wrapper/README.md](wrapper/README.md) for more information about the wrapper scripts.

