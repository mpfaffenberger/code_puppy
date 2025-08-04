# Contributing to Code Puppy - Walmart Edition

Thank you for your interest in contributing to Code Puppy! This project thrives on community involvement. Whether you want to add a new feature, fix a bug, or improve documentation, your help is welcome.

## Table of Contents
- [Contributing to Code Puppy - Walmart Edition](#contributing-to-code-puppy---walmart-edition)
  - [Table of Contents](#table-of-contents)
  - [Getting Started](#getting-started)
  - [Development Workflow](#development-workflow)
    - [Useful Development Scripts](#useful-development-scripts)
      - [code-puppy-dev](#code-puppy-dev)
      - [build\_install\_local\_whl.sh](#build_install_local_whlsh)
      - [pretty\_print\_path.sh](#pretty_print_pathsh)
      - [run\_pre\_commit.sh](#run_pre_commitsh)
  - [Adding a New Feature](#adding-a-new-feature)
  - [Fixing a Bug](#fixing-a-bug)
  - [Testing](#testing)
  - [Pre-commit](#pre-commit)
  - [Code Style](#code-style)
  - [Submitting Your Changes](#submitting-your-changes)
  - [Code of Conduct](#code-of-conduct)
  - [Legal](#legal)
  - [Licensing Agreement](#licensing-agreement)

---

## Getting Started

1. **Set up your environment:**
   - Code Puppy uses `Python` and the `uv` package manager.
   - Ensure you have Python 3.10 or higher.
   ```sh
   python --version
   # or
   python3 --version
   ```
   - install uv. Follow the [instructions](https://docs.astral.sh/uv/getting-started/installation/#__tabbed_1_1) for your machine OS

   - create a virtual environment and activate it
    ```sh
    uv venv
    source .venv/bin/activate
    ```
    - NOTE: if you cd out of code-puppy, run `deactivate` to deactivate the virtual environment

    OR, if you prefer activate/deactivate to happen automatically, use `direnv` (see below)

    <details>
    <summary><strong>Use direnv (optional)</strong></summary>

    - Install direnv
    ```shell
    brew install direnv
    ```
    - First time you cd into this project you will be prompted to run:
    ```shell
    direnv allow
    ```
    NOTE: `.envrc` file contains the logic for that:
    ```sh
    layout_uv() {
      local venv_path=".venv"
      if [ ! -d "$venv_path" ]; then
        uv venv
      fi
      source "$venv_path/bin/activate"
    }

    layout uv

    PYTHON_VERSION="$(python --version)"
    echo "$(tput setaf 3)Virtual env (.venv) $PYTHON_VERSION activated $(tput sgr0)"
    ```
    Here is what the experience looks like

    ```sh
      ~/workspace/github-wm
      > cd code-puppy
      direnv: loading ~/workspace/github-wm/code-puppy/.envrc
      Virtual env (.venv) Python 3.13.0 activated
      direnv: export +VIRTUAL_ENV +VIRTUAL_ENV_PROMPT ~PATH
      (.venv) ~/workspace/github-wm/code-puppy  ↰ main
      > which python
      /Users/l0m0eby/workspace/github-wm/code-puppy/.venv/bin/python
      > cd
      direnv: unloading
      > which python
      /Users/l0m0eby/.pyenv/shims/python
    ```

    </details>

2. **Clone the repository:**
   ```sh
   git clone git@gecgithub01.walmart.com:genaica/code-puppy.git
   cd code-puppy
   ```


3. **Install dependencies:**
   ```sh
   uv sync
   ```
   - MCP features require configuration in `~/.code_puppy/mcp_servers.json` (see documentation for examples).

4. **Setup UV_INDEX_URL**
   - add this to your ~/.zshrc, or the equivalent for your shell
   ```
   export UV_INDEX_URL=https://pypi.ci.artifacts.walmart.com/artifactory/api/pypi/external-pypi/simple

   source ~/.zshrc
   ```

5. **Run code-puppy:**

   Use one of these commands:
   ```sh
   NO_VERSION_UPDATE=1 uv run code-puppy
   NO_VERSION_UPDATE=1 uv run code-puppy --interactive
   NO_VERSION_UPDATE=1 uv run code-puppy --tui
   NO_VERSION_UPDATE=1 uv run code-puppy --web
   ```
   Note: also, see `code-puppy-dev` below.

## Development Workflow

- **Create a new branch** for your work:
  ```sh
  git checkout -b feature/your-feature-name
  # or for bugfixes
  git checkout -b fix/short-description
  # or for documentation
  git checkout -b docs/short-description
  ```
- **Keep your branch up to date** with `main`:
  ```sh
  git fetch origin
  git rebase origin/main
  ```

### Useful Development Scripts

The project contains several utility scripts to help with development:

#### code-puppy-dev

This script reinstalls code-puppy in development mode and runs it with the provided arguments, making it perfect for testing changes immediately after making them.

**Purpose:**
- Reinstalls the code-puppy package in development mode (`-e` flag)
- Runs code-puppy with the current code changes
- Passes through any arguments you provide

**When to use:**
- During active development when you're frequently making changes
- When you want to test your changes immediately without manual reinstallation
- For quick iterations during feature development or bug fixing

**How to use:**
```sh
# Run with TUI interface
./code-puppy-dev --tui

# Run with web interface
./code-puppy-dev --web

# Run with interactive console interface
./code-puppy-dev --interactive

# Run with any other arguments
./code-puppy-dev "prompt or command"
```

**How it works:**
1. Builds and reinstalls code-puppy in development mode using `uv pip install --no-deps --reinstall -e .`
2. Runs code-puppy with your changes using `NO_VERSION_UPDATE=1 uv run code-puppy`
3. Passes through any command-line arguments you provided


#### build_install_local_whl.sh

This script builds a wheel file from your local code-puppy repository and installs it globally, allowing you to test how your changes would behave in a user's environment.

**Purpose:**
- Builds a new code_puppy wheel file from your current local code
- Uninstalls any existing global code-puppy installation
- Re-installs from the newly created wheel file

**When to use:**
- When you want to test how your changes would behave after a user installs code-puppy
- For testing compatibility with the global installation process
- Before submitting a PR that changes installation behavior

**How to use:**
```sh
./scripts/build_install_local_whl.sh
```

**Prerequisites:**
- uv installed and in your PATH
- pip or pip3 installed and in your PATH
- VPN connection (for accessing internal package repositories)

After running, it will provide a command to run your newly installed version:
```sh
NO_VERSION_UPDATE=1 ~/.code-puppy-venv/bin/code-puppy
```

#### pretty_print_path.sh

This script displays your PATH environment variable in a readable format, helping you debug PATH-related issues.

**Purpose:**
- Shows all directories in your PATH in a structured format
- Identifies duplicate entries and their positions
- Checks for non-existent directories in your PATH
- Shows the location of common executables (python, pip, node, npm, git, uv)

**When to use:**
- When troubleshooting environment setup issues
- When you suspect PATH conflicts or incorrect ordering
- To verify which versions of tools are being used

**How to use:**
```sh
./scripts/pretty_print_path.sh
```

The output includes:
- A numbered list of all PATH entries
- Summary statistics (total entries, unique directories, duplicates)
- Validation warnings for non-existent directories
- Locations of common executables

#### run_pre_commit.sh

This script runs pre-commit hooks in a loop until they all pass, handling cases where pre-commit fixes issues that reveal new issues.

**Purpose:**
- Runs `uv --native-tls run pre-commit run --all-files` repeatedly until successful
- Automatically handles iterative fixes (e.g., formatter fixes code that then fails linting)
- Provides progress feedback and attempt tracking
- Eliminates the need to manually re-run pre-commit multiple times

**When to use:**
- Before committing changes to ensure all pre-commit hooks pass
- After making large code changes that might trigger multiple formatting/linting fixes
- When setting up pre-commit hooks for the first time on existing code
- As part of your development workflow to maintain code quality

**How to use:**
```sh
./scripts/run_pre_commit.sh
```

**What it does:**
1. Runs pre-commit hooks on all files
2. If hooks fail (non-zero exit code), waits 1 second and tries again
3. Continues looping until all hooks pass (exit code 0)
4. Shows attempt numbers and helpful status messages
5. Celebrates when everything is clean! 🎉

**Why this is useful:**
Pre-commit hooks often fix issues automatically (like code formatting), but these fixes can sometimes reveal new issues (like newly formatted code that now fails linting rules). This script handles those cascading fixes automatically.

## Adding a New Feature

- Open an issue (optional but recommended) to discuss your idea with maintainers.
- Implement your feature following the existing architecture:
   - For external tool integration, prefer configuration-based approaches (see MCP server support).
   - Update or add configuration examples if needed.
- Document your feature in the README or relevant docs.
- Add or update tests to cover your new feature.

## Fixing a Bug

- Check for existing issues or open a new one describing the bug.
- Create a branch and write a failing test that reproduces the bug (if possible).
- Fix the bug and ensure all tests pass.
- Update documentation if the fix changes behavior.

## Testing

- Code Puppy maintains **95%+ test coverage**. All new code must include appropriate tests.
- Run tests locally:
  ```sh
  uv sync
  pytest
  ```
- Format your code:
  ```sh
  ruff format .
  ```
- Lint your code:
  ```sh
  ruff check .
  ```

## Pre-commit
- before adding a commit, run the pre-commit checks:
  ```sh
  uv --native-tls run pre-commit run --all-files
  ```

## Code Style

- Follow Python's [PEP 8](https://www.python.org/dev/peps/pep-0008/) for coding style.
- Use descriptive commit messages.
- Keep pull requests focused and concise.

## Submitting Your Changes

- Publish your branch:
   ```sh
   git push origin <your-branch>
   ```
- Open a Pull Request against the `main` branch.
- Describe your changes: `QodoMerge` is setup on this repo and should generate this automatically (`/describe` command)
- Participate in code review and address feedback promptly.

## Code of Conduct

This project adheres to the [Contributor Covenant code of conduct](https://www.contributor-covenant.org/version/2/0/code_of_conduct/). By participating, you are expected to uphold this code.

## Legal
- All code submissions are subject to our dual-license model: Contributions pre July 7, 2025, fall under MIT license; post July 7, 2025, are Walmart proprietary properties.

## Licensing Agreement
- By contributing, you agree that your contributions will be dual-licensed under the relevant terms mentioned in the [LICENSE](LICENSE) file.


---

Thank you for helping make Code Puppy better!
