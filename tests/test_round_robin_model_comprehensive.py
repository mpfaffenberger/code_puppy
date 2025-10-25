"""Comprehensive unit tests for code_puppy.round_robin_model.

Full coverage of round-robin model distribution logic.
"""
import pytest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, Mock
from code_puppy.round_robin_model import RoundRobinModel


class MockModel:
    """Mock model for testing."""
    
    def __init__(self, name, system_prompt="default", base_url=None, settings=None):
        self._name = name
        self._system = system_prompt
        self._base_url = base_url
        self._settings = settings or {}
        self.request = AsyncMock(return_value=f"response_{name}")
        self.request_stream = self._create_mock_stream()
        self.customize_request_parameters = Mock(side_effect=lambda x: x)
    
    @property
    def model_name(self):
        return self._name
    
    @property
    def system(self):
        return self._system
    
    @property
    def base_url(self):
        return self._base_url
    
    @property
    def settings(self):
        return self._settings
    
    def _create_mock_stream(self):
        @asynccontextmanager
        async def mock_stream(*args, **kwargs):
            yield f"stream_{self._name}"
        return mock_stream
    
    def model_attributes(self, model):
        return {"model_name": self._name}


class TestInitialization:
    """Test RoundRobinModel initialization - 6 tests."""
    
    def test_init_with_single_model(self):
        model = MockModel("model1")
        rr = RoundRobinModel(model)
        assert len(rr.models) == 1
        assert rr._current_index == 0
        assert rr._rotate_every == 1
    
    def test_init_with_multiple_models(self):
        m1, m2, m3 = MockModel("m1"), MockModel("m2"), MockModel("m3")
        rr = RoundRobinModel(m1, m2, m3)
        assert len(rr.models) == 3
    
    def test_init_requires_at_least_one_model(self):
        with pytest.raises(ValueError, match="At least one model"):
            RoundRobinModel()
    
    def test_init_rotate_every_must_be_positive(self):
        m1 = MockModel("m1")
        with pytest.raises(ValueError, match="rotate_every must be at least 1"):
            RoundRobinModel(m1, rotate_every=0)


class TestProperties:
    """Test properties - 7 tests."""
    
    def test_model_name_single_model(self):
        rr = RoundRobinModel(MockModel("gpt-4"))
        assert rr.model_name == "round_robin:gpt-4"
    
    def test_model_name_multiple_models(self):
        rr = RoundRobinModel(MockModel("gpt-4"), MockModel("claude-3"))
        assert rr.model_name == "round_robin:gpt-4,claude-3"
    
    def test_model_name_with_custom_rotate_every(self):
        rr = RoundRobinModel(MockModel("m1"), MockModel("m2"), rotate_every=3)
        assert rr.model_name == "round_robin:m1,m2:rotate_every=3"
    
    def test_system_property(self):
        rr = RoundRobinModel(MockModel("m1", system_prompt="System 1"))
        assert rr.system == "System 1"
    
    def test_base_url_property(self):
        rr = RoundRobinModel(MockModel("m1", base_url="https://api.example.com"))
        assert rr.base_url == "https://api.example.com"


class TestRotationLogic:
    """Test rotation logic - 5 tests."""
    
    def test_rotation_wraps_around(self):
        m1, m2, m3 = MockModel("m1"), MockModel("m2"), MockModel("m3")
        rr = RoundRobinModel(m1, m2, m3)
        
        assert rr._get_next_model() is m1
        assert rr._get_next_model() is m2
        assert rr._get_next_model() is m3
        assert rr._get_next_model() is m1  # Wraps
    
    def test_single_model_no_rotation(self):
        m1 = MockModel("m1")
        rr = RoundRobinModel(m1)
        
        for _ in range(10):
            assert rr._get_next_model() is m1
        assert rr._current_index == 0


class TestRequestMethod:
    """Test request method - 7 tests."""
    
    @pytest.mark.asyncio
    async def test_request_rotates_between_models(self):
        m1, m2 = MockModel("m1"), MockModel("m2")
        rr = RoundRobinModel(m1, m2)
        
        await rr.request([], None, MagicMock())
        assert m1.request.call_count == 1
        
        await rr.request([], None, MagicMock())
        assert m2.request.call_count == 1
        
        await rr.request([], None, MagicMock())
        assert m1.request.call_count == 2
    
    @pytest.mark.asyncio
    async def test_request_propagates_exceptions(self):
        m1 = MockModel("m1")
        m1.request.side_effect = ValueError("Error")
        rr = RoundRobinModel(m1)
        
        with pytest.raises(ValueError, match="Error"):
            await rr.request([], None, MagicMock())
    
    @pytest.mark.asyncio
    async def test_request_does_not_fallback_on_error(self):
        m1, m2 = MockModel("m1"), MockModel("m2")
        m1.request.side_effect = RuntimeError("Failed")
        rr = RoundRobinModel(m1, m2)
        
        with pytest.raises(RuntimeError, match="Failed"):
            await rr.request([], None, MagicMock())
        
        m2.request.assert_not_called()


class TestRequestStreamMethod:
    """Test request_stream - 3 tests."""
    
    @pytest.mark.asyncio
    async def test_request_stream_rotates(self):
        m1, m2 = MockModel("m1"), MockModel("m2")
        rr = RoundRobinModel(m1, m2)
        
        async with rr.request_stream([], None, MagicMock()) as stream:
            assert stream == "stream_m1"
        
        async with rr.request_stream([], None, MagicMock()) as stream:
            assert stream == "stream_m2"


class TestIntegration:
    """Integration tests - 2 tests."""
    
    @pytest.mark.asyncio
    async def test_full_round_robin_cycle(self):
        m1, m2, m3 = MockModel("m1"), MockModel("m2"), MockModel("m3")
        rr = RoundRobinModel(m1, m2, m3, rotate_every=2)
        
        # Model1 x 2
        await rr.request([], None, MagicMock())
        await rr.request([], None, MagicMock())
        assert m1.request.call_count == 2
        
        # Model2 x 2
        await rr.request([], None, MagicMock())
        await rr.request([], None, MagicMock())
        assert m2.request.call_count == 2
        
        # Model3 x 2
        await rr.request([], None, MagicMock())
        await rr.request([], None, MagicMock())
        assert m3.request.call_count == 2
        
        # Wraps back to model1
        await rr.request([], None, MagicMock())
        assert m1.request.call_count == 3

