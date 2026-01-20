# Publishing Guide

This document provides step-by-step instructions for publishing Synesis to TestPyPI and PyPI.

## Prerequisites

Ensure you have the required tools installed:

```bash
pip install --upgrade build twine
```

## Pre-Publication Checklist

- [ ] All tests pass: `pytest`
- [ ] Version number updated in `pyproject.toml`
- [ ] `CHANGELOG.md` updated with release notes
- [ ] Documentation up to date
- [ ] No uncommitted changes: `git status`

## Building the Package

### 1. Clean Previous Builds

```bash
# Remove old distribution files
rm -rf dist/ build/ *.egg-info

# On Windows:
# rmdir /s /q dist build synesis.egg-info
```

### 2. Build Distribution

```bash
python -m build
```

This creates:
- `dist/synesis-0.1.0.tar.gz` (source distribution)
- `dist/synesis-0.1.0-py3-none-any.whl` (wheel)

### 3. Verify Build

```bash
# Check distribution metadata
twine check dist/*

# Inspect package contents
tar -tzf dist/synesis-0.1.0.tar.gz

# On Windows, use 7-Zip or:
# python -m tarfile -l dist/synesis-0.1.0.tar.gz
```

Expected contents:
- `synesis/` (package code)
- `synesis/grammar/synesis.lark` (grammar file)
- `LICENSE`, `README.md`, `CHANGELOG.md`
- `pyproject.toml`

## Publishing to TestPyPI

TestPyPI is a sandbox for testing package uploads without affecting the production PyPI.

### 1. Create TestPyPI Account

Register at: https://test.pypi.org/account/register/

### 2. Generate API Token

1. Go to https://test.pypi.org/manage/account/token/
2. Create token with scope "Entire account"
3. Save the token securely (starts with `pypi-`)

### 3. Configure Credentials

Create or edit `~/.pypirc`:

```ini
[testpypi]
username = __token__
password = pypi-YOUR_TOKEN_HERE
```

### 4. Upload to TestPyPI

```bash
twine upload --repository testpypi dist/*
```

### 5. Test Installation

```bash
# Create a new virtual environment
python -m venv test-env
source test-env/bin/activate  # On Windows: test-env\Scripts\activate

# Install from TestPyPI
pip install -i https://test.pypi.org/simple/ synesis

# Test the package
synesis --version
synesis --help

# Deactivate and remove test environment
deactivate
rm -rf test-env
```

## Publishing to PyPI (Production)

⚠️ **Warning**: PyPI uploads are **permanent**. You cannot delete or overwrite a release.

### 1. Create PyPI Account

Register at: https://pypi.org/account/register/

### 2. Generate API Token

1. Go to https://pypi.org/manage/account/token/
2. Create token with scope "Entire account" (or project-specific after first upload)
3. Save the token securely

### 3. Configure Credentials

Update `~/.pypirc`:

```ini
[pypi]
username = __token__
password = pypi-YOUR_TOKEN_HERE

[testpypi]
username = __token__
password = pypi-YOUR_TESTPYPI_TOKEN_HERE
```

### 4. Upload to PyPI

```bash
twine upload dist/*
```

### 5. Verify Installation

```bash
pip install synesis
synesis --version
```

## Post-Publication Tasks

### 1. Create Git Tag

```bash
git tag -a v0.1.0 -m "Release version 0.1.0"
git push origin v0.1.0
```

### 2. Create GitHub Release

1. Go to https://github.com/synesis-lang/synesis/releases
2. Click "Create a new release"
3. Select tag `v0.1.0`
4. Title: `Synesis v0.1.0 - Initial Release`
5. Description: Copy relevant sections from `CHANGELOG.md`
6. Attach distribution files from `dist/`
7. Publish release

### 3. Update Version for Development

In `pyproject.toml`, increment version:

```toml
version = "0.1.1-dev"
```

Commit:

```bash
git add pyproject.toml
git commit -m "chore: bump version to 0.1.1-dev"
git push
```

## Common Issues

### Issue: `twine upload` fails with 403 Forbidden

**Solution**: Check API token permissions. Ensure token has upload permissions for the project.

### Issue: Package name conflict

**Solution**: PyPI package names are unique globally. If `synesis` is taken, consider alternatives:
- `synesis-lang`
- `synesis-compiler`
- Contact current owner if name is abandoned

### Issue: Missing files in distribution

**Solution**: Verify `MANIFEST.in` includes all necessary files:

```ini
include LICENSE README.md CHANGELOG.md
recursive-include synesis *.lark
```

Rebuild and check:

```bash
python -m build
tar -tzf dist/synesis-*.tar.gz
```

### Issue: Import errors after installation

**Solution**:
1. Check `pyproject.toml` has correct package discovery:
   ```toml
   [tool.setuptools.packages.find]
   where = ["."]
   include = ["synesis*"]
   ```
2. Ensure `synesis/__init__.py` exists
3. Test in clean environment

## Automation with GitHub Actions

The included `.github/workflows/ci.yml` automatically:
- Runs tests on push/PR
- Builds distribution
- Validates package with `twine check`

To add automated PyPI publishing on tag creation, add to `.github/workflows/ci.yml`:

```yaml
name: Publish to PyPI

on:
  push:
    tags:
      - 'v*'

jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: '3.10'
    - name: Build
      run: |
        pip install build
        python -m build
    - name: Publish to PyPI
      uses: pypa/gh-action-pypi-publish@release/v1
      with:
        password: ${{ secrets.PYPI_API_TOKEN }}
```

Add `PYPI_API_TOKEN` to GitHub repository secrets.

## Resources

- **TestPyPI**: https://test.pypi.org
- **PyPI**: https://pypi.org
- **Twine Documentation**: https://twine.readthedocs.io
- **Python Packaging Guide**: https://packaging.python.org
- **Semantic Versioning**: https://semver.org

## Version Numbering

Synesis follows Semantic Versioning (SemVer):

- `MAJOR.MINOR.PATCH` (e.g., `1.2.3`)
- **MAJOR**: Breaking changes (e.g., grammar changes, API redesign)
- **MINOR**: New features, backward-compatible (e.g., new export formats)
- **PATCH**: Bug fixes, backward-compatible (e.g., error message improvements)

Development versions: `0.1.1-dev`, `0.2.0-alpha`, `1.0.0-beta`

---

For questions or issues with publishing, contact the maintainers at the [GitHub repository](https://github.com/synesis-lang/synesis).
