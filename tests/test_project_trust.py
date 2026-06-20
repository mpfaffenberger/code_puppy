import json
from pathlib import Path
from unittest.mock import patch

from code_puppy.project_trust import (
    ensure_project_trusted,
    filter_untrusted_project_paths,
    get_project_trust,
    get_trust_scope,
    is_domain_trusted,
    is_path_trusted,
    is_url_trusted,
    set_project_trusted,
    set_trust_scope,
)


class _NonTty:
    def isatty(self):
        return False


def test_unknown_noninteractive_project_fails_closed(tmp_path: Path):
    with (
        patch(
            "code_puppy.project_trust._trust_file", return_value=tmp_path / "trust.json"
        ),
        patch("code_puppy.project_trust.sys.stdin", new=_NonTty()),
    ):
        assert ensure_project_trusted(tmp_path / "repo") is False
        assert not (tmp_path / "trust.json").exists()


def test_trust_decision_round_trip_is_keyed_by_canonical_path(tmp_path: Path):
    trust_file = tmp_path / "trust.json"
    project = tmp_path / "repo"
    project.mkdir()
    with patch("code_puppy.project_trust._trust_file", return_value=trust_file):
        set_project_trusted(project / ".", True)
        assert get_project_trust(project) is True

    assert json.loads(trust_file.read_text())[str(project.resolve())] is True


def test_environment_override_takes_precedence(tmp_path: Path):
    with (
        patch(
            "code_puppy.project_trust._trust_file", return_value=tmp_path / "trust.json"
        ),
        patch.dict("os.environ", {"CODE_PUPPY_TRUST_PROJECT": "true"}),
    ):
        assert ensure_project_trusted(tmp_path / "repo", prompt=False) is True


def test_untrusted_project_resource_paths_are_filtered(tmp_path: Path):
    project = tmp_path / "repo"
    user_path = tmp_path / "user-skills"
    project.mkdir()
    with (
        patch("code_puppy.project_trust.Path.cwd", return_value=project),
        patch("code_puppy.project_trust.ensure_project_trusted", return_value=False),
    ):
        assert filter_untrusted_project_paths(
            [user_path, project / ".mist" / "skills"]
        ) == [str(user_path)]


def test_scoped_trust_upgrades_legacy_boolean_record(tmp_path: Path):
    trust_file = tmp_path / "trust.json"
    project = tmp_path / "repo"
    project.mkdir()
    with (
        patch("code_puppy.project_trust._trust_file", return_value=trust_file),
        patch("code_puppy.project_trust._git_remotes", return_value=()),
    ):
        set_project_trusted(project, True)
        scope = set_trust_scope(
            project,
            domains=["API.EXAMPLE.COM"],
            services=["internal-ci"],
        )
        assert scope.trusted is True
        assert is_domain_trusted("sub.api.example.com", project)
        assert is_url_trusted("https://api.example.com/v1", project)
        assert get_trust_scope(project).services == ("internal-ci",)
    raw = json.loads(trust_file.read_text())[str(project.resolve())]
    assert raw["trusted"] is True


def test_trusted_paths_stay_inside_project(tmp_path: Path):
    trust_file = tmp_path / "trust.json"
    project = tmp_path / "repo"
    project.mkdir()
    with patch("code_puppy.project_trust._trust_file", return_value=trust_file):
        set_project_trusted(project, True)
        assert is_path_trusted(project / "src" / "app.py", project)
        assert not is_path_trusted(tmp_path / "outside.txt", project)


def test_git_remotes_extend_default_scope(tmp_path: Path):
    trust_file = tmp_path / "trust.json"
    project = tmp_path / "repo"
    project.mkdir()
    with (
        patch("code_puppy.project_trust._trust_file", return_value=trust_file),
        patch(
            "code_puppy.project_trust._git_remotes",
            return_value=("git@github.com:example/mist.git",),
        ),
    ):
        set_project_trusted(project, True)
        scope = get_trust_scope(project)
    assert scope.domains == ("github.com",)
    assert scope.scm_orgs == ("example",)
