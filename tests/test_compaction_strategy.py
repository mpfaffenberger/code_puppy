import configparser
import os
import tempfile
from unittest.mock import patch

from code_puppy.config import (
    DEFAULT_SECTION,
    get_compaction_strategy,
)


def test_default_compaction_strategy():
    """Test that the default compaction strategy is truncation"""
    with patch("code_puppy.config.get_value") as mock_get_value:
        mock_get_value.return_value = None
        strategy = get_compaction_strategy()
        assert strategy == "truncation"


def test_set_compaction_strategy_truncation():
    """Test that we can set the compaction strategy to truncation"""
    import code_puppy.config

    original_config_dir = code_puppy.config.CONFIG_DIR
    original_config_file = code_puppy.config.CONFIG_FILE

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            code_puppy.config.CONFIG_DIR = temp_dir
            code_puppy.config.CONFIG_FILE = os.path.join(temp_dir, "puppy.cfg")

            config = configparser.ConfigParser()
            config[DEFAULT_SECTION] = {}
            config[DEFAULT_SECTION]["compaction_strategy"] = "truncation"

            with open(code_puppy.config.CONFIG_FILE, "w") as f:
                config.write(f)

            strategy = get_compaction_strategy()
            assert strategy == "truncation"
        finally:
            code_puppy.config.CONFIG_DIR = original_config_dir
            code_puppy.config.CONFIG_FILE = original_config_file


def test_set_compaction_strategy_summarization():
    """Test that we can set the compaction strategy to summarization"""
    import code_puppy.config

    original_config_dir = code_puppy.config.CONFIG_DIR
    original_config_file = code_puppy.config.CONFIG_FILE

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            code_puppy.config.CONFIG_DIR = temp_dir
            code_puppy.config.CONFIG_FILE = os.path.join(temp_dir, "puppy.cfg")

            config = configparser.ConfigParser()
            config[DEFAULT_SECTION] = {}
            config[DEFAULT_SECTION]["compaction_strategy"] = "summarization"

            with open(code_puppy.config.CONFIG_FILE, "w") as f:
                config.write(f)

            strategy = get_compaction_strategy()
            assert strategy == "summarization"
        finally:
            code_puppy.config.CONFIG_DIR = original_config_dir
            code_puppy.config.CONFIG_FILE = original_config_file


def test_set_compaction_strategy_invalid():
    """Test that an invalid compaction strategy defaults to truncation"""
    import code_puppy.config

    original_config_dir = code_puppy.config.CONFIG_DIR
    original_config_file = code_puppy.config.CONFIG_FILE

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            code_puppy.config.CONFIG_DIR = temp_dir
            code_puppy.config.CONFIG_FILE = os.path.join(temp_dir, "puppy.cfg")

            config = configparser.ConfigParser()
            config[DEFAULT_SECTION] = {}
            config[DEFAULT_SECTION]["compaction_strategy"] = "invalid_strategy"

            with open(code_puppy.config.CONFIG_FILE, "w") as f:
                config.write(f)

            strategy = get_compaction_strategy()
            assert strategy == "truncation"
        finally:
            code_puppy.config.CONFIG_DIR = original_config_dir
            code_puppy.config.CONFIG_FILE = original_config_file
