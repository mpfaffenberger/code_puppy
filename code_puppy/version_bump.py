import toml


def bump_version(pyproject_path):
    # Load pyproject.toml
    with open(pyproject_path, 'r') as f:
        pyproject = toml.load(f)

    # Parse the version
    version = pyproject['project']['version']

    # Update __init__.py with the new version
    with open('code_puppy/__init__.py', 'w') as f:
        f.write(f"__version__ = '{version}'\n")
    print(f'Updated __init__.py to version {version}')
