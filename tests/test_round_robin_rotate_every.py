from unittest.mock import AsyncMock, MagicMock

import pytest

from code_puppy.round_robin_model import RoundRobinModel


class MockModel:
    """A simple mock model that implements the required interface."""

    def __init__(self, name, settings=None):
        self._name = name
        self._settings = settings
        self.request = AsyncMock(return_value=f"response_from_{name}")

    @property
    def model_name(self):
        return self._name

    @property
    def settings(self):
        return self._settings

    def customize_request_parameters(self, model_request_parameters):
        return model_request_parameters


@pytest.mark.asyncio
async def test_round_robin_rotate_every_default():
    """Test that round-robin model rotates every request by default."""
    # Create mock models
    model1 = MockModel("model1")
    model2 = MockModel("model2")

    # Create round-robin model with default rotate_every (1)
    rr_model = RoundRobinModel(model1, model2)

    # Verify model name format
    assert rr_model.model_name == "round_robin:model1,model2"

    # First request should go to model1
    await rr_model.request([], None, MagicMock())
    model1.request.assert_called_once()
    model2.request.assert_not_called()

    # Second request should go to model2 (rotated)
    await rr_model.request([], None, MagicMock())
    model1.request.assert_called_once()
    model2.request.assert_called_once()


@pytest.mark.asyncio
async def test_round_robin_rotate_every_custom():
    """Test that round-robin model rotates every N requests when specified."""
    # Create mock models
    model1 = MockModel("model1")
    model2 = MockModel("model2")

    # Create round-robin model with rotate_every=3
    rr_model = RoundRobinModel(model1, model2, rotate_every=3)

    # Verify model name format includes rotate_every parameter
    assert rr_model.model_name == "round_robin:model1,model2:rotate_every=3"

    # First 3 requests should all go to model1
    for i in range(3):
        await rr_model.request([], None, MagicMock())

    assert model1.request.call_count == 3
    assert model2.request.call_count == 0

    # Reset mocks to clear call counts
    model1.request.reset_mock()
    model2.request.reset_mock()

    # Next 3 requests should all go to model2
    for i in range(3):
        await rr_model.request([], None, MagicMock())

    assert model1.request.call_count == 0
    assert model2.request.call_count == 3

    # Reset mocks again
    model1.request.reset_mock()
    model2.request.reset_mock()

    # Next request should go back to model1
    await rr_model.request([], None, MagicMock())

    assert model1.request.call_count == 1
    assert model2.request.call_count == 0


def test_round_robin_rotate_every_validation():
    """Test that rotate_every parameter is validated correctly."""
    model1 = MockModel("model1")
    model2 = MockModel("model2")

    # Should raise ValueError for rotate_every < 1
    with pytest.raises(ValueError, match="rotate_every must be at least 1"):
        RoundRobinModel(model1, model2, rotate_every=0)

    with pytest.raises(ValueError, match="rotate_every must be at least 1"):
        RoundRobinModel(model1, model2, rotate_every=-1)

    # Should work fine for rotate_every >= 1
    rr_model = RoundRobinModel(model1, model2, rotate_every=1)
    assert rr_model._rotate_every == 1

    rr_model = RoundRobinModel(model1, model2, rotate_every=5)
    assert rr_model._rotate_every == 5
