import os
import pytest
from code_puppy.model_factory import ModelFactory

import json

TEST_CONFIG_PATH = os.path.join(os.path.dirname(__file__), '../code_puppy/models.json')


def test_ollama_load_model():
    config = ModelFactory.load_config(TEST_CONFIG_PATH)

    # Skip test if 'ollama-llama2' model is not in config
    if 'ollama-llama2' not in config:
        pytest.skip("Model 'ollama-llama2' not found in configuration, skipping test.")

    model = ModelFactory.get_model('ollama-llama2', config)
    assert hasattr(model, 'provider')
    assert model.provider.model_name == 'llama2'
    assert 'chat' in dir(model), 'OllamaModel must have a .chat method!'

# Optionally, a future test can actually attempt to make an async call, but that would require a running Ollama backend, so... let's not.
