from unittest.mock import AsyncMock, MagicMock

import pytest

from code_puppy.round_robin_model import RoundRobinModel


class MockModel:
    """A simple mock model that implements the required interface."""

    def __init__(self, name, settings=None):
        self._name = name
        self._settings = settings
        self.request = AsyncMock(return_value=f"response_from_{name}")
        self.request_stream = MagicMock()
        self.customize_request_parameters = lambda x: x

    @property
    def model_name(self):
        return self._name

    @property
    def settings(self):
        return self._settings

    @property
    def system(self):
        return f"system_{self._name}"

    @property
    def base_url(self):
        return f"https://api.{self._name}.com"

    def model_attributes(self, model):
        return {"model_name": self._name}

    def prepare_request(self, model_settings, model_request_parameters):
        """Mock prepare_request that returns settings and params as-is."""
        return model_settings, model_request_parameters


class TestRoundRobinModel:
    def test_initialization(self):
        """Test basic initialization with models."""
        models = [MockModel("model1"), MockModel("model2")]
        rrm = RoundRobinModel(*models)

        assert rrm is not None
        assert len(rrm.models) == 2
        assert rrm._current_index == 0
        assert rrm._request_count == 0
        assert rrm._rotate_every == 1

    def test_initialization_with_settings(self):
        """Test initialization with model settings."""
        models = [MockModel("model1"), MockModel("model2")]
        settings = {"temperature": 0.7}
        rrm = RoundRobinModel(*models, settings=settings)

        assert rrm.settings == settings

    def test_initialization_empty_models_raises_error(self):
        """Test that initialization fails with no models."""
        with pytest.raises(ValueError, match="At least one model must be provided"):
            RoundRobinModel()

    def test_initialization_single_model(self):
        """Test initialization with a single model."""
        model = MockModel("single_model")
        rrm = RoundRobinModel(model)

        assert len(rrm.models) == 1
        assert rrm._current_index == 0
        assert rrm.model_name == "round_robin:single_model"

    def test_rotation_basic(self):
        """Test basic rotation between two models."""
        models = [MockModel("model1"), MockModel("model2")]
        rrm = RoundRobinModel(*models, rotate_every=1)

        # First call should return model1
        current_model = rrm._get_next_model()
        assert current_model.model_name == "model1"
        assert rrm._current_index == 1
        assert rrm._request_count == 0

        # Second call should return model2
        current_model = rrm._get_next_model()
        assert current_model.model_name == "model2"
        assert rrm._current_index == 0
        assert rrm._request_count == 0

        # Third call should return model1 again (cycle)
        current_model = rrm._get_next_model()
        assert current_model.model_name == "model1"
        assert rrm._current_index == 1
        assert rrm._request_count == 0

    def test_rotation_three_models(self):
        """Test rotation through three models."""
        models = [MockModel("m1"), MockModel("m2"), MockModel("m3")]
        rrm = RoundRobinModel(*models, rotate_every=1)

        expected_sequence = ["m1", "m2", "m3", "m1", "m2", "m3"]
        actual_sequence = []

        for _ in range(6):
            model = rrm._get_next_model()
            actual_sequence.append(model.model_name)

        assert actual_sequence == expected_sequence

    def test_rotation_with_rotate_every_2(self):
        """Test rotation with rotate_every=2."""
        models = [MockModel("model1"), MockModel("model2")]
        rrm = RoundRobinModel(*models, rotate_every=2)

        # First two calls should return model1
        assert rrm._get_next_model().model_name == "model1"
        assert rrm._get_next_model().model_name == "model1"
        assert rrm._current_index == 1

        # Next two calls should return model2
        assert rrm._get_next_model().model_name == "model2"
        assert rrm._get_next_model().model_name == "model2"
        assert rrm._current_index == 0

    def test_single_model_no_rotation(self):
        """Test that single model always returns same model regardless of rotate_every."""
        model = MockModel("single")
        rrm = RoundRobinModel(model, rotate_every=3)

        for _ in range(10):
            returned_model = rrm._get_next_model()
            assert returned_model is model
            assert rrm._current_index == 0  # Should never change

    def test_model_name_property(self):
        """Test model_name property formatting."""
        models = [MockModel("m1"), MockModel("m2"), MockModel("m3")]

        # Default rotate_every=1
        rrm = RoundRobinModel(*models)
        assert rrm.model_name == "round_robin:m1,m2,m3"

        # Custom rotate_every
        rrm_custom = RoundRobinModel(*models, rotate_every=5)
        assert rrm_custom.model_name == "round_robin:m1,m2,m3:rotate_every=5"

    def test_properties_delegate_to_current_model(self):
        """Test that system and base_url properties delegate to current model."""
        models = [MockModel("model1"), MockModel("model2")]
        rrm = RoundRobinModel(*models)

        # Initially should point to model1
        assert rrm.system == "system_model1"
        assert rrm.base_url == "https://api.model1.com"

        # After rotation should point to model2
        rrm._get_next_model()  # Rotate to model2
        assert rrm.system == "system_model2"
        assert rrm.base_url == "https://api.model2.com"

    def test_request_count_tracking(self):
        """Test that request count is tracked correctly."""
        models = [MockModel("model1"), MockModel("model2")]
        rrm = RoundRobinModel(*models, rotate_every=3)

        # First call
        rrm._get_next_model()
        assert rrm._request_count == 1
        assert rrm._current_index == 0

        # Second call
        rrm._get_next_model()
        assert rrm._request_count == 2
        assert rrm._current_index == 0

        # Third call - should trigger rotation
        rrm._get_next_model()
        assert rrm._request_count == 0  # Reset after rotation
        assert rrm._current_index == 1

    @pytest.mark.asyncio
    async def test_request_method_uses_rotation(self):
        """Test that request() method uses rotation correctly."""
        models = [MockModel("model1"), MockModel("model2")]
        rrm = RoundRobinModel(*models)

        # Make multiple requests
        await rrm.request([], None, MagicMock())
        await rrm.request([], None, MagicMock())
        await rrm.request([], None, MagicMock())

        # Should have called each model once, then model1 again
        assert models[0].request.call_count == 2
        assert models[1].request.call_count == 1

    def test_invalid_rotate_every_values(self):
        """Test validation of rotate_every parameter."""
        models = [MockModel("model1"), MockModel("model2")]

        with pytest.raises(ValueError, match="rotate_every must be at least 1"):
            RoundRobinModel(*models, rotate_every=0)

        with pytest.raises(ValueError, match="rotate_every must be at least 1"):
            RoundRobinModel(*models, rotate_every=-5)

    def test_large_rotate_every_value(self):
        """Test behavior with large rotate_every values."""
        models = [MockModel("m1"), MockModel("m2")]
        rrm = RoundRobinModel(*models, rotate_every=100)

        # Should stay on first model for 99 calls (count goes 1-99)
        for _ in range(99):
            assert rrm._get_next_model().model_name == "m1"
        assert rrm._request_count == 99
        assert rrm._current_index == 0

        # 100th call should trigger rotation (count becomes 100 >= rotate_every)
        assert (
            rrm._get_next_model().model_name == "m1"
        )  # Still returns m1, but rotates after
        assert rrm._current_index == 1
        assert rrm._request_count == 0  # Reset after rotation

        # Next call should return m2
        assert rrm._get_next_model().model_name == "m2"
