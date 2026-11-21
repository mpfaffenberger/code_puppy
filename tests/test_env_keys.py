"""What a project's `.env` may set, and what a saved key store exports.

`pup` is often started in a repository someone else wrote, so its `.env` is
untrusted input: it may carry the credentials the user keeps there, and
nothing that would send their prompts somewhere else or move Code Puppy's
own folders.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from code_puppy import api_keys, main

CREDENTIALS = ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "E2B_API_KEY", "GITHUB_TOKEN"]
REFUSED = [
    # Where requests go: the prompts, the files read, and the provider's key.
    "OPENAI_BASE_URL",
    "ANTHROPIC_BASE_URL",
    "AZURE_OPENAI_ENDPOINT",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "ALL_PROXY",
    # Where Code Puppy reads its own settings, plugins and sign-ins.
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_STATE_HOME",
    "CODE_PUPPY_NO_SPLASH",
    "CLAI_NO_SPLASH",
    "CLAUDE_CODE_NO_UPDATE_CHECK",
    # A value spliced into outgoing requests.
    "OPENAI_DEFAULT_HEADERS",
]


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A cloned repository, with `pup` started inside it."""
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.chdir(repo)
    for name in [*CREDENTIALS, *REFUSED]:
        monkeypatch.delenv(name, raising=False)
    yield repo


def write_env(repo: Path, **values: str) -> None:
    repo.joinpath(".env").write_text(
        "".join(f"{name}={value}\n" for name, value in values.items()), encoding="utf-8"
    )


@pytest.mark.parametrize("name", CREDENTIALS)
def test_a_credential_in_the_projects_env_is_used(name: str, repository: Path) -> None:
    write_env(repository, **{name: "from-the-env"})

    main._load_dotenv()

    assert os.environ[name] == "from-the-env"


@pytest.mark.parametrize("name", REFUSED)
def test_the_project_cannot_set_anything_else(name: str, repository: Path) -> None:
    write_env(repository, OPENAI_API_KEY="k", **{name: "http://attacker.example"})

    main._load_dotenv()

    assert name not in os.environ
    assert os.environ["OPENAI_API_KEY"] == "k", "the credentials still load"


def test_what_the_user_set_themselves_wins(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "mine")
    write_env(repository, OPENAI_API_KEY="theirs")

    main._load_dotenv()

    assert os.environ["OPENAI_API_KEY"] == "mine"


def test_an_env_in_a_parent_directory_is_read_from_a_subdirectory(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_env(repository, OPENAI_API_KEY="from-the-root")
    inside = repository / "src" / "deep"
    inside.mkdir(parents=True)
    monkeypatch.chdir(inside)

    main._load_dotenv()

    assert os.environ["OPENAI_API_KEY"] == "from-the-root"


def test_a_directory_named_env_is_not_read(repository: Path) -> None:
    """`find_dotenv` names a path; only a file is read, so a pipe cannot block startup."""
    repository.joinpath(".env").mkdir()

    main._load_dotenv()  # does not raise


def test_an_unreadable_env_is_reported_and_startup_goes_on(
    repository: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_env(repository, OPENAI_API_KEY="k")

    def explode(*args: object, **kwargs: object) -> dict[str, str]:
        raise OSError("device not ready")

    monkeypatch.setattr("dotenv.dotenv_values", explode)

    main._load_dotenv()

    assert "Ignoring `.env`" in capsys.readouterr().err
    assert "OPENAI_API_KEY" not in os.environ


# --- the saved key store ----------------------------------------------------


def test_saved_credentials_are_exported_and_other_labels_are_not() -> None:
    """`/keys` names are labels; only one shaped like a credential is a variable."""
    from pydantic_ai_pax.config.api_keys import save_key

    for name in ("OPENAI_API_KEY", "GH_TOKEN", "SOME_KEY"):
        save_key(name=name, value=f"{name.lower()}-secret")
    environ: dict[str, str] = {}

    assert sorted(api_keys.export_saved_keys(environ)) == ["GH_TOKEN", "OPENAI_API_KEY"]
    assert environ == {
        "GH_TOKEN": "gh_token-secret",
        "OPENAI_API_KEY": "openai_api_key-secret",
    }


def test_without_a_saved_bundle_the_key_store_is_not_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Opening it may prompt for the OS keyring; most users never saved a key."""
    opened: list[str] = []

    def load_keys() -> dict[str, object]:
        opened.append("load_keys")
        return {}

    monkeypatch.setattr("pydantic_ai_pax.config.api_keys.load_keys", load_keys)

    assert api_keys.export_saved_keys({}) == []
    assert opened == []


@pytest.mark.parametrize(
    ("name", "credential"),
    [
        ("OPENAI_API_KEY", True),
        ("GITHUB_TOKEN", True),
        ("MY_SERVICE_API_KEY", True),
        ("OPENAI_BASE_URL", False),
        ("API_KEY_FOR_NOTHING", False),
        ("XDG_CONFIG_HOME", False),
    ],
)
def test_credential_names_are_those_ending_in_key_or_token(
    name: str, credential: bool
) -> None:
    assert api_keys.is_credential_name(name) is credential
