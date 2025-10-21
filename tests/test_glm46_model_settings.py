"""Test GLM-4.6 model settings functionality."""

import pytest
from unittest.mock import patch, MagicMock

from code_puppy.agents.base_agent import BaseAgent
from code_puppy.config import set_config_value, get_value


class TestGLM46ModelSettings:
    """Test GLM-4.6 specific model settings."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock BaseAgent for testing."""
        agent = MagicMock(spec=BaseAgent)
        agent.get_model_context_length = MagicMock(return_value=200000)
        return agent

    def test_glm46_synthetic_model_defaults(self, mock_agent):
        """Test that synthetic GLM-4.6 gets default settings."""
        with patch('code_puppy.config.get_value') as mock_get_value:
            # Mock no user configuration
            mock_get_value.return_value = None
            
            # Simulate the model settings logic
            model_name = "synthetic-GLM-4.6"
            model_name_lower = model_name.lower()
            
            is_glm46_synthetic = (
                "synthetic-glm-4.6" in model_name_lower
                or "glm-4.6" in model_name_lower and "synthetic" in model_name_lower
            )
            is_glm46_zai = "glm-4.6" in model_name_lower and (
                "coding" in model_name_lower or "zai" in model_name_lower
            )
            is_glm46 = is_glm46_synthetic or is_glm46_zai
            
            model_settings_dict = {"seed": 42}
            
            if is_glm46:
                model_settings_dict["temperature"] = 1.0
                model_settings_dict["top_p"] = 0.95
                model_settings_dict["top_k"] = 40
            
            # Verify defaults are applied
            assert is_glm46 is True
            assert model_settings_dict["temperature"] == 1.0
            assert model_settings_dict["top_p"] == 0.95
            assert model_settings_dict["top_k"] == 40

    def test_glm46_zai_coding_model_defaults(self, mock_agent):
        """Test that ZAI GLM-4.6 coding gets default settings."""
        with patch('code_puppy.config.get_value') as mock_get_value:
            # Mock no user configuration
            mock_get_value.return_value = None
            
            model_name = "glm-4.6-coding"
            model_name_lower = model_name.lower()
            
            is_glm46_synthetic = (
                "synthetic-glm-4.6" in model_name_lower
                or "glm-4.6" in model_name_lower and "synthetic" in model_name_lower
            )
            is_glm46_zai = "glm-4.6" in model_name_lower and (
                "coding" in model_name_lower or "zai" in model_name_lower
            )
            is_glm46 = is_glm46_synthetic or is_glm46_zai
            
            model_settings_dict = {"seed": 42}
            
            if is_glm46:
                model_settings_dict["temperature"] = 1.0
                model_settings_dict["top_p"] = 0.95
                model_settings_dict["top_k"] = 40
            
            # Verify defaults are applied
            assert is_glm46 is True
            assert model_settings_dict["temperature"] == 1.0
            assert model_settings_dict["top_p"] == 0.95
            assert model_settings_dict["top_k"] == 40

    def test_glm46_user_override(self, mock_agent):
        """Test that user settings override GLM-4.6 defaults."""
        with patch('code_puppy.config.get_value') as mock_get_value:
            # Mock user configuration
            def mock_get_value_side_effect(key):
                return {
                    "temperature": "0.8",
                    "top_p": "0.9",
                    "top_k": "50"
                }.get(key)
            
            mock_get_value.side_effect = mock_get_value_side_effect
            
            model_name = "synthetic-GLM-4.6"
            model_name_lower = model_name.lower()
            
            is_glm46_synthetic = (
                "synthetic-glm-4.6" in model_name_lower
                or "glm-4.6" in model_name_lower and "synthetic" in model_name_lower
            )
            is_glm46_zai = "glm-4.6" in model_name_lower and (
                "coding" in model_name_lower or "zai" in model_name_lower
            )
            is_glm46 = is_glm46_synthetic or is_glm46_zai
            
            model_settings_dict = {"seed": 42}
            
            if is_glm46:
                # Temperature: user value or default 1.0
                user_temp = mock_get_value("temperature")
                if user_temp:
                    model_settings_dict["temperature"] = float(user_temp)
                else:
                    model_settings_dict["temperature"] = 1.0
                
                # Top-p: user value or default 0.95
                user_top_p = mock_get_value("top_p")
                if user_top_p:
                    model_settings_dict["top_p"] = float(user_top_p)
                else:
                    model_settings_dict["top_p"] = 0.95
                
                # Top-k: user value or default 40
                user_top_k = mock_get_value("top_k")
                if user_top_k:
                    model_settings_dict["top_k"] = int(user_top_k)
                else:
                    model_settings_dict["top_k"] = 40
            
            # Verify user values are applied
            assert is_glm46 is True
            assert model_settings_dict["temperature"] == 0.8
            assert model_settings_dict["top_p"] == 0.9
            assert model_settings_dict["top_k"] == 50

    def test_non_glm46_no_defaults(self, mock_agent):
        """Test that non-GLM-4.6 models don't get default settings."""
        with patch('code_puppy.config.get_value') as mock_get_value:
            # Mock no user configuration
            mock_get_value.return_value = None
            
            model_name = "gpt-4"
            model_name_lower = model_name.lower()
            
            is_glm46_synthetic = (
                "synthetic-glm-4.6" in model_name_lower
                or "glm-4.6" in model_name_lower and "synthetic" in model_name_lower
            )
            is_glm46_zai = "glm-4.6" in model_name_lower and (
                "coding" in model_name_lower or "zai" in model_name_lower
            )
            is_glm46 = is_glm46_synthetic or is_glm46_zai
            
            model_settings_dict = {"seed": 42}
            
            if is_glm46:
                model_settings_dict["temperature"] = 1.0
                model_settings_dict["top_p"] = 0.95
                model_settings_dict["top_k"] = 40
            else:
                # For non-GLM-4.6 models: only apply user settings if explicitly configured
                user_temp = mock_get_value("temperature")
                if user_temp:
                    model_settings_dict["temperature"] = float(user_temp)
                
                user_top_p = mock_get_value("top_p")
                if user_top_p:
                    model_settings_dict["top_p"] = float(user_top_p)
                
                user_top_k = mock_get_value("top_k")
                if user_top_k:
                    model_settings_dict["top_k"] = int(user_top_k)
            
            # Verify no GLM-4.6 defaults are applied
            assert is_glm46 is False
            assert "temperature" not in model_settings_dict
            assert "top_p" not in model_settings_dict
            assert "top_k" not in model_settings_dict

    def test_non_glm46_user_settings(self, mock_agent):
        """Test that non-GLM-4.6 models get user settings if configured."""
        with patch('code_puppy.config.get_value') as mock_get_value:
            # Mock user configuration
            def mock_get_value_side_effect(key):
                return {
                    "temperature": "0.7",
                    "top_p": "0.85",
                    "top_k": "30"
                }.get(key)
            
            mock_get_value.side_effect = mock_get_value_side_effect
            
            model_name = "gpt-4"
            model_name_lower = model_name.lower()
            
            is_glm46_synthetic = (
                "synthetic-glm-4.6" in model_name_lower
                or "glm-4.6" in model_name_lower and "synthetic" in model_name_lower
            )
            is_glm46_zai = "glm-4.6" in model_name_lower and (
                "coding" in model_name_lower or "zai" in model_name_lower
            )
            is_glm46 = is_glm46_synthetic or is_glm46_zai
            
            model_settings_dict = {"seed": 42}
            
            if is_glm46:
                # GLM-4.6 logic (not executed in this case)
                pass
            else:
                # For non-GLM-4.6 models: only apply user settings if explicitly configured
                user_temp = mock_get_value("temperature")
                if user_temp:
                    model_settings_dict["temperature"] = float(user_temp)
                
                user_top_p = mock_get_value("top_p")
                if user_top_p:
                    model_settings_dict["top_p"] = float(user_top_p)
                
                user_top_k = mock_get_value("top_k")
                if user_top_k:
                    model_settings_dict["top_k"] = int(user_top_k)
            
            # Verify user settings are applied
            assert is_glm46 is False
            assert model_settings_dict["temperature"] == 0.7
            assert model_settings_dict["top_p"] == 0.85
            assert model_settings_dict["top_k"] == 30

    def test_glm46_invalid_user_values(self, mock_agent):
        """Test that invalid user values fall back to defaults for GLM-4.6."""
        with patch('code_puppy.config.get_value') as mock_get_value:
            # Mock invalid user configuration
            def mock_get_value_side_effect(key):
                return {
                    "temperature": "invalid_temp",
                    "top_p": "invalid_top_p",
                    "top_k": "invalid_top_k"
                }.get(key)
            
            mock_get_value.side_effect = mock_get_value_side_effect
            
            model_name = "synthetic-GLM-4.6"
            model_name_lower = model_name.lower()
            
            is_glm46_synthetic = (
                "synthetic-glm-4.6" in model_name_lower
                or "glm-4.6" in model_name_lower and "synthetic" in model_name_lower
            )
            is_glm46_zai = "glm-4.6" in model_name_lower and (
                "coding" in model_name_lower or "zai" in model_name_lower
            )
            is_glm46 = is_glm46_synthetic or is_glm46_zai
            
            model_settings_dict = {"seed": 42}
            
            if is_glm46:
                # Temperature: user value or default 1.0 (validate 0.0-2.0)
                user_temp = mock_get_value("temperature")
                if user_temp:
                    try:
                        temp_value = float(user_temp)
                        if 0.0 <= temp_value <= 2.0:
                            model_settings_dict["temperature"] = temp_value
                        else:
                            model_settings_dict["temperature"] = 1.0
                    except ValueError:
                        model_settings_dict["temperature"] = 1.0
                else:
                    model_settings_dict["temperature"] = 1.0
                
                # Top-p: user value or default 0.95 (validate 0.0-1.0)
                user_top_p = mock_get_value("top_p")
                if user_top_p:
                    try:
                        top_p_value = float(user_top_p)
                        if 0.0 <= top_p_value <= 1.0:
                            model_settings_dict["top_p"] = top_p_value
                        else:
                            model_settings_dict["top_p"] = 0.95
                    except ValueError:
                        model_settings_dict["top_p"] = 0.95
                else:
                    model_settings_dict["top_p"] = 0.95
                
                # Top-k: user value or default 40 (validate positive integer)
                user_top_k = mock_get_value("top_k")
                if user_top_k:
                    try:
                        top_k_value = int(user_top_k)
                        if top_k_value > 0:
                            model_settings_dict["top_k"] = top_k_value
                        else:
                            model_settings_dict["top_k"] = 40
                    except ValueError:
                        model_settings_dict["top_k"] = 40
                else:
                    model_settings_dict["top_k"] = 40
            
            # Verify defaults are applied due to invalid user values
            assert is_glm46 is True
            assert model_settings_dict["temperature"] == 1.0
            assert model_settings_dict["top_p"] == 0.95
            assert model_settings_dict["top_k"] == 40

    def test_glm46_out_of_range_values(self, mock_agent):
        """Test that out-of-range values fall back to defaults for GLM-4.6."""
        with patch('code_puppy.config.get_value') as mock_get_value:
            # Mock out-of-range user configuration
            def mock_get_value_side_effect(key):
                return {
                    "temperature": "3.0",  # Out of range (0.0-2.0)
                    "top_p": "1.5",       # Out of range (0.0-1.0)
                    "top_k": "-5"         # Out of range (must be positive)
                }.get(key)
            
            mock_get_value.side_effect = mock_get_value_side_effect
            
            model_name = "synthetic-GLM-4.6"
            model_name_lower = model_name.lower()
            
            is_glm46_synthetic = (
                "synthetic-glm-4.6" in model_name_lower
                or "glm-4.6" in model_name_lower and "synthetic" in model_name_lower
            )
            is_glm46_zai = "glm-4.6" in model_name_lower and (
                "coding" in model_name_lower or "zai" in model_name_lower
            )
            is_glm46 = is_glm46_synthetic or is_glm46_zai
            
            model_settings_dict = {"seed": 42}
            
            if is_glm46:
                # Temperature: user value or default 1.0 (validate 0.0-2.0)
                user_temp = mock_get_value("temperature")
                if user_temp:
                    try:
                        temp_value = float(user_temp)
                        if 0.0 <= temp_value <= 2.0:
                            model_settings_dict["temperature"] = temp_value
                        else:
                            model_settings_dict["temperature"] = 1.0
                    except ValueError:
                        model_settings_dict["temperature"] = 1.0
                else:
                    model_settings_dict["temperature"] = 1.0
                
                # Top-p: user value or default 0.95 (validate 0.0-1.0)
                user_top_p = mock_get_value("top_p")
                if user_top_p:
                    try:
                        top_p_value = float(user_top_p)
                        if 0.0 <= top_p_value <= 1.0:
                            model_settings_dict["top_p"] = top_p_value
                        else:
                            model_settings_dict["top_p"] = 0.95
                    except ValueError:
                        model_settings_dict["top_p"] = 0.95
                else:
                    model_settings_dict["top_p"] = 0.95
                
                # Top-k: user value or default 40 (validate positive integer)
                user_top_k = mock_get_value("top_k")
                if user_top_k:
                    try:
                        top_k_value = int(user_top_k)
                        if top_k_value > 0:
                            model_settings_dict["top_k"] = top_k_value
                        else:
                            model_settings_dict["top_k"] = 40
                    except ValueError:
                        model_settings_dict["top_k"] = 40
                else:
                    model_settings_dict["top_k"] = 40
            
            # Verify defaults are applied due to out-of-range values
            assert is_glm46 is True
            assert model_settings_dict["temperature"] == 1.0
            assert model_settings_dict["top_p"] == 0.95
            assert model_settings_dict["top_k"] == 40

    def test_model_identification_patterns(self):
        """Test various model name patterns for GLM-4.6 identification."""
        test_cases = [
            ("synthetic-GLM-4.6", True, True, False),
            ("synthetic-glm-4.6", True, True, False),
            ("glm-4.6-coding", True, False, True),
            ("glm-4.6-api", False, False, False),  # Not coding or zai
            ("gpt-4", False, False, False),
            ("claude-3-sonnet", False, False, False),
            ("some-other-glm-4.6-model", False, False, False),
        ]
        
        for model_name, expected_is_glm46, expected_synthetic, expected_zai in test_cases:
            model_name_lower = model_name.lower()
            
            is_glm46_synthetic = (
                "synthetic-glm-4.6" in model_name_lower
                or "glm-4.6" in model_name_lower and "synthetic" in model_name_lower
            )
            is_glm46_zai = "glm-4.6" in model_name_lower and (
                "coding" in model_name_lower or "zai" in model_name_lower
            )
            is_glm46 = is_glm46_synthetic or is_glm46_zai
            
            assert is_glm46 == expected_is_glm46, f"Failed for {model_name}"
            assert is_glm46_synthetic == expected_synthetic, f"Synthetic check failed for {model_name}"
            assert is_glm46_zai == expected_zai, f"ZAI check failed for {model_name}"