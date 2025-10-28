# patch_via_gerrit - Gerrit Patch Application Tool

`patch_via_gerrit` is a command-line tool for applying Gerrit code reviews to a `repo sync` workspace. It automates the process of fetching and applying patches from Gerrit, including automatic dependency resolution for related reviews.

## Installation

The easiest way to install `patch_via_gerrit` is using `uv`:

```bash
uv tool install patch-via-gerrit
```

This will install `patch_via_gerrit` to `~/.local/bin/` (or the equivalent on Windows). Make sure this directory is on your `PATH`.

### Alternative: Using the Wrapper Script

For CI/CD environments or systems where you don't want to pre-install tools, you can use the wrapper script which automatically installs and updates `patch_via_gerrit` via `uv`:

**Linux/macOS:**
```bash
curl -qLsSf https://packages.couchbase.com/patch_via_gerrit/latest/patch_via_gerrit -O
chmod +x patch_via_gerrit
./patch_via_gerrit --help
```

**Windows:**
```powershell
# Download patch_via_gerrit.exe from packages.couchbase.com
.\patch_via_gerrit.exe --help
```

The wrapper script will automatically install `uv` if needed, then install/update `patch_via_gerrit` itself.

## Configuration

Before using `patch_via_gerrit`, you need to create a configuration file with your Gerrit credentials. By default, the tool looks for `~/.ssh/patch_via_gerrit.ini`:

```ini
[main]
gerrit_url = http://review.couchbase.org
username = myuser
password = abcdefghijklmnopqrstuvwxyz0123456789012345
```

**Note:** The `password` field should contain an HTTP password generated from your Gerrit account settings (Settings → HTTP Credentials), not your actual account password.

You can also specify a custom configuration file location with the `-c/--config` option.

## Usage

By default, `patch_via_gerrit` operates on the current directory. You can either navigate to your `repo sync` workspace first, or use the `-s/--source` option to specify the workspace location.

### Apply Patches by Review ID

Apply one or more specific review IDs:

```bash
patch_via_gerrit -r 134808
patch_via_gerrit -r 134808,134809
patch_via_gerrit --review-id 134808 134809
```

### Apply Patches by Change ID

Apply all open reviews with a specific Change-Id:

```bash
patch_via_gerrit -g Ic2e7bfd58bd4fcf3be5330338f9376f1a958cf6a
patch_via_gerrit --change-id I1234567890abcdef
```

### Apply Patches by Topic

Apply all open reviews with a specific topic:

```bash
patch_via_gerrit -t my-feature
patch_via_gerrit --topic feature-xyz
```

### Multiple Gerrit Instances

The tool supports both the main Couchbase Gerrit and the AsterixDB Gerrit instance. Prefix reviews with `asterixdb:` to use the AsterixDB instance:

```bash
patch_via_gerrit -r 134808,asterixdb:20503
patch_via_gerrit -t my-topic,asterixdb:asterix-feature
```

### Additional Options

**Checkout vs Cherry-Pick:**
By default, patches are cherry-picked. Use `-C/--checkout` to checkout the review instead:

```bash
patch_via_gerrit -C -r 134808
```

**Source Directory:**
Apply patches to a different repo sync location:

```bash
patch_via_gerrit -s /path/to/repo/sync -r 134808
```

**Manifest Handling:**
```bash
# Ignore changes to the manifest repository
patch_via_gerrit --ignore-manifest -r 134808

# Apply only changes to the manifest repository
patch_via_gerrit --only-manifest -r 134808
```

**Branch Whitelisting:**
By default, only reviews matching the manifest's branch (or on the `unstable` branch) are applied. Add more branches to the whitelist:

```bash
patch_via_gerrit -w unstable,experimental -r 134808
```

**Debug Output:**
```bash
patch_via_gerrit -d -r 134808
patch_via_gerrit --debug -r 134808
```

## How It Works

`patch_via_gerrit` automates several tasks:

1. **Dependency Resolution:** When you specify a review, the tool automatically finds:
   - Related reviews with the same Change-Id
   - Reviews with the same topic
   - Parent reviews that the requested review depends on

2. **Branch Filtering:** Reviews are only applied if their target branch matches the manifest's revision for that project, or if the branch is whitelisted (default: `unstable`).

3. **Manifest Updates:** If any patches modify the `manifest` repository itself, the tool applies those first and runs `repo sync` to update the workspace before applying remaining patches.

4. **Verification:** The tool verifies that all explicitly-requested reviews were successfully applied.

## Command-Line Options

```
patch_via_gerrit [options]

Required (mutually exclusive):
  -r, --review-id ID [ID ...]     Review IDs to apply (comma-separated)
  -g, --change-id ID [ID ...]     Change IDs to apply (comma-separated)
  -t, --topic TOPIC [TOPIC ...]   Topics to apply (comma-separated)

Options:
  -d, --debug                     Enable debugging output
  -c, --config FILE               Configuration file (default: ~/.ssh/patch_via_gerrit.ini)
  -s, --source DIR                Location of repo sync checkout (default: current directory)
  -C, --checkout                  Checkout reviews instead of cherry-picking
  -w, --whitelist-branches BRANCH [BRANCH ...]
                                  Branches to allow even if they don't match manifest
  --ignore-manifest               Don't apply changes to manifest repository
  --only-manifest                 Apply only changes to manifest repository
  -V, --version                   Display version information
```

## Troubleshooting

**"Configuration file missing":**
- Create `~/.ssh/patch_via_gerrit.ini` with your Gerrit credentials
- Or specify a custom location with `-c/--config`

**"Query returns no data for review ID":**
- The review ID doesn't exist or is marked "private"
- Verify the review ID on the Gerrit web interface

**"Project missing on disk":**
- Ensure you've run `repo sync` before applying patches
- The review may reference a project not in your manifest groups

**"Failed to apply all explicitly-requested review IDs":**
- There may be merge conflicts
- The project may be locked to a specific SHA in the manifest
- Try running with `--debug` to see more details

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for information about development, testing, and publishing.

## License

See [LICENSE](LICENSE) for license information.
