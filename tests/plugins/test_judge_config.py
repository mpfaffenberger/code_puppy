"""Tests for the persisted judge config registry."""

from __future__ import annotations

import json
import os
import tempfile

import pytest
from unittest.mock import patch

from code_puppy.plugins.wiggum import judge_config
from code_puppy.plugins.wiggum.judge_config import (
    DEFAULT_JUDGE_PROMPT,
    JudgeConfig,
    add_judge,
    delete_judge,
    get_enabled_judges_or_default,
    load_judges,
    save_judges,
    toggle_judge,
    update_judge,
    validate_name,
    JudgeRegistry,
)


@pytest.fixture
def isolated_judges_file():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "judges.json")
        with patch.object(judge_config, "JUDGES_FILE", path):
            yield path


def test_validate_name_accepts_simple_identifiers():
    assert validate_name("abc") is None
    assert validate_name("abc-123") is None
    assert validate_name("abc_def_42") is None


def test_validate_name_rejects_bad_names():
    assert validate_name("") is not None
    assert validate_name("has space") is not None
    assert validate_name("with.dot") is not None
    assert validate_name("x" * 65) is not None  # too long


def test_load_judges_returns_empty_when_no_file(isolated_judges_file):
    registry = load_judges()
    assert isinstance(registry, JudgeRegistry)
    assert registry.judges == []


def test_load_judges_returns_empty_on_garbage_json(isolated_judges_file):
    with open(isolated_judges_file, "w", encoding="utf-8") as f:
        f.write("not json {{{")
    assert load_judges().judges == []


def test_load_judges_skips_invalid_entries(isolated_judges_file):
    with open(isolated_judges_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "judges": [
                    {"name": "ok", "model": "x", "prompt": "p", "enabled": True},
                    {"name": "bad name", "model": "x"},  # invalid name
                    {"name": "no-model", "model": ""},  # missing model
                    {"name": "ok", "model": "y"},  # duplicate
                ]
            },
            f,
        )
    registry = load_judges()
    assert [j.name for j in registry.judges] == ["ok"]


def test_add_and_load_round_trip(isolated_judges_file):
    add_judge(JudgeConfig(name="alpha", model="gpt-5.4", prompt="p1"))
    add_judge(JudgeConfig(name="beta", model="claude", prompt="p2", enabled=False))

    reg = load_judges()
    assert reg.names() == ["alpha", "beta"]
    assert reg.find("alpha").model == "gpt-5.4"
    assert reg.find("beta").enabled is False
    assert reg.enabled() == [reg.find("alpha")]


def test_add_judge_rejects_duplicate(isolated_judges_file):
    add_judge(JudgeConfig(name="x", model="m"))
    with pytest.raises(ValueError, match="already exists"):
        add_judge(JudgeConfig(name="x", model="other"))


def test_add_judge_rejects_invalid_name(isolated_judges_file):
    with pytest.raises(ValueError, match="must be"):
        add_judge(JudgeConfig(name="bad name", model="m"))


def test_add_judge_rejects_empty_model(isolated_judges_file):
    with pytest.raises(ValueError, match="Model must not be empty"):
        add_judge(JudgeConfig(name="x", model=""))


def test_update_judge_changes_fields(isolated_judges_file):
    add_judge(JudgeConfig(name="x", model="m1", prompt="p1", enabled=True))

    update_judge("x", model="m2", prompt="p2", enabled=False)

    judge = load_judges().find("x")
    assert judge.model == "m2"
    assert judge.prompt == "p2"
    assert judge.enabled is False


def test_update_judge_rename(isolated_judges_file):
    add_judge(JudgeConfig(name="x", model="m"))
    update_judge("x", new_name="y")
    names = load_judges().names()
    assert "y" in names and "x" not in names


def test_update_judge_rename_conflict(isolated_judges_file):
    add_judge(JudgeConfig(name="x", model="m"))
    add_judge(JudgeConfig(name="y", model="m"))
    with pytest.raises(ValueError, match="already exists"):
        update_judge("x", new_name="y")


def test_update_judge_invalid_rename(isolated_judges_file):
    add_judge(JudgeConfig(name="x", model="m"))
    with pytest.raises(ValueError, match="must be"):
        update_judge("x", new_name="bad name")


def test_update_judge_missing(isolated_judges_file):
    with pytest.raises(ValueError, match="No judge"):
        update_judge("nope", model="m")


def test_update_judge_rejects_empty_model(isolated_judges_file):
    add_judge(JudgeConfig(name="x", model="m"))
    with pytest.raises(ValueError, match="Model must not be empty"):
        update_judge("x", model="")


def test_update_judge_resets_empty_prompt_to_default(isolated_judges_file):
    add_judge(JudgeConfig(name="x", model="m", prompt="custom"))
    update_judge("x", prompt="")
    assert load_judges().find("x").prompt == DEFAULT_JUDGE_PROMPT


def test_delete_judge(isolated_judges_file):
    add_judge(JudgeConfig(name="x", model="m"))
    add_judge(JudgeConfig(name="y", model="m"))
    assert delete_judge("x") is True
    assert load_judges().names() == ["y"]
    assert delete_judge("nope") is False


def test_toggle_judge(isolated_judges_file):
    add_judge(JudgeConfig(name="x", model="m", enabled=True))
    assert toggle_judge("x") is False
    assert load_judges().find("x").enabled is False
    assert toggle_judge("x") is True
    assert load_judges().find("x").enabled is True
    assert toggle_judge("nope") is None


def test_get_enabled_judges_or_default_uses_configured(isolated_judges_file):
    add_judge(JudgeConfig(name="a", model="m1"))
    add_judge(JudgeConfig(name="b", model="m2", enabled=False))

    judges = get_enabled_judges_or_default("fallback-model")
    assert [j.name for j in judges] == ["a"]


def test_get_enabled_judges_or_default_falls_back(isolated_judges_file):
    # no judges configured
    judges = get_enabled_judges_or_default("fallback-model")
    assert len(judges) == 1
    assert judges[0].name == "default"
    assert judges[0].model == "fallback-model"
    assert judges[0].enabled is True
    assert judges[0].prompt == DEFAULT_JUDGE_PROMPT


def test_get_enabled_judges_or_default_falls_back_when_all_disabled(
    isolated_judges_file,
):
    add_judge(JudgeConfig(name="x", model="m", enabled=False))
    judges = get_enabled_judges_or_default("fallback-model")
    assert len(judges) == 1
    assert judges[0].name == "default"


def test_save_judges_is_atomic(isolated_judges_file):
    add_judge(JudgeConfig(name="x", model="m"))
    # No leftover tmp file
    assert not os.path.exists(isolated_judges_file + ".tmp")


def test_save_judges_creates_parent_dir(tmp_path):
    nested = tmp_path / "nested" / "deeper" / "judges.json"
    with patch.object(judge_config, "JUDGES_FILE", str(nested)):
        save_judges(JudgeRegistry(judges=[JudgeConfig(name="x", model="m")]))
        assert nested.exists()
