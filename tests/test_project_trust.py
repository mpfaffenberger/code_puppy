import json
from pathlib import Path
from unittest.mock import patch

from code_puppy.project_trust import (
    ensure_project_trusted,
    filter_untrusted_project_paths,
    get_project_trust,
    set_project_trusted,
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
