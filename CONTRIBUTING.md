# Contributing to Code Puppy - Walmart Edition

Thank you for your interest in contributing to Code Puppy! This project thrives on community involvement. Whether you want to add a new feature, fix a bug, or improve documentation, your help is welcome.

## Table of Contents
- [Contributing to Code Puppy - Walmart Edition](#contributing-to-code-puppy---walmart-edition)
  - [Table of Contents](#table-of-contents)
  - [Getting Started](#getting-started)
  - [Development Workflow](#development-workflow)
  - [Adding a New Feature](#adding-a-new-feature)
  - [Fixing a Bug](#fixing-a-bug)
  - [Testing](#testing)
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
      ~
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