from unittest.mock import patch

from prompt_toolkit.document import Document

import code_puppy.command_line.model_picker_completion as mpc
from code_puppy.command_line.model_picker_completion import ModelNameCompleter


def test_load_model_names_reads_json():
    models = {"gpt4": {}, "llama": {}}
    # Mock the ModelFactory.load_config to return our test models
    with patch(
        "code_puppy.command_line.model_picker_completion.ModelFactory.load_config",
        return_value=models,
    ):
        out = mpc.load_model_names()
        assert set(out) == set(models.keys())


def test_set_and_get_active_model_updates_config():
    with patch.object(mpc, "set_model_name") as set_mock:
        with patch.object(mpc, "get_model_name", return_value="foo"):
            mpc.set_active_model("foo")
            set_mock.assert_called_with("foo")
            assert mpc.get_active_model() == "foo"


def test_model_name_completer():
    models = ["alpha", "bravo"]
    with patch.object(mpc, "load_model_names", return_value=models):
        comp = ModelNameCompleter(trigger="~m")
        doc = Document(text="foo ~m", cursor_position=6)
        completions = list(comp.get_completions(doc, None))
        assert {c.text for c in completions} == set(models)
