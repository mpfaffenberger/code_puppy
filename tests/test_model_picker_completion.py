import os
import json
import tempfile
from unittest.mock import patch
from prompt_toolkit.document import Document
import code_puppy.command_line.model_picker_completion as mpc
from code_puppy.command_line.model_picker_completion import ModelNameCompleter


def temp_models_json(models):
    fd, fname = tempfile.mkstemp()
    os.close(fd)
    with open(fname, "w") as f:
        json.dump(models, f)
    return fname


def test_load_model_names_reads_json():
    models = {"gpt4": {}, "llama": {}}
    models_path = temp_models_json(models)
    with patch.dict(os.environ, {"MODELS_JSON_PATH": models_path}):
        old_json_path = mpc.MODELS_JSON_PATH
        mpc.MODELS_JSON_PATH = models_path
        try:
            out = mpc.load_model_names()
            assert set(out) == set(models.keys())
        finally:
            mpc.MODELS_JSON_PATH = old_json_path
    os.remove(models_path)


def test_set_and_get_active_model_updates_env():
    with patch.object(mpc, "set_model_name") as set_mock:
        with patch.object(mpc, "get_model_name", return_value="foo"):
            mpc.set_active_model("foo")
            set_mock.assert_called_with("foo")
            assert os.environ["MODEL_NAME"] == "foo"
            assert mpc.get_active_model() == "foo"


def test_model_name_completer():
    models = ["alpha", "bravo"]
    with patch.object(mpc, "load_model_names", return_value=models):
        comp = ModelNameCompleter(trigger="~m")
        doc = Document(text="foo ~m", cursor_position=6)
        completions = list(comp.get_completions(doc, None))
        assert {c.text for c in completions} == set(models)
