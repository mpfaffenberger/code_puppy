# Releasing Fast Puppy

PyPI publishing is driven by GitHub Releases.

The package version in `pyproject.toml` is the source of truth. The release
workflow refuses to publish if the GitHub release tag does not match that
version, or if the version already exists on PyPI.

## Prepare a Version

```bash
uv run python scripts/prepare_release.py 0.1.2
```

The script updates:

- `pyproject.toml`
- `uv.lock`

It also checks PyPI before changing files so you do not prepare a version that
has already been published.

## Verify Locally

```bash
uv lock --check
uv run ruff check --fix
uv run ruff format .
uv build
```

## Publish

Commit the version change and push it to `main`:

```bash
git add pyproject.toml uv.lock
git commit -m "Release 0.1.2"
git push origin main
```

Tag the exact commit that contains the matching `pyproject.toml` version:

```bash
git tag v0.1.2
git push origin v0.1.2
```

Create and publish a GitHub Release for that tag. Publishing the GitHub Release
starts `.github/workflows/publish.yml`, which runs tests, builds the package,
and uploads to PyPI through trusted publishing.

For a package version `0.1.2`, use:

- Git tag: `v0.1.2`
- GitHub Release title: `v0.1.2`
- `pyproject.toml` version: `0.1.2`

Do not re-run a published version. PyPI package files are immutable, so every
publish needs a new version number.
