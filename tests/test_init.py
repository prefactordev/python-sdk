"""Tests for public API."""

import prefactor_sdk
from prefactor_sdk import get_tracer, init
from prefactor_sdk.config import Config


class TestInit:
    """Test init() function (middleware API)."""

    def setup_method(self):
        """Reset global state before each test."""
        prefactor_sdk._global_tracer = None
        prefactor_sdk._global_handler = None
        prefactor_sdk._global_middleware = None

    def test_init_basic(self):
        """Test basic initialization."""
        init()

        # Should be able to get tracer
        tracer = get_tracer()
        assert tracer is not None

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = Config(
            transport_type="stdio",
            sample_rate=0.5,
        )

        init(config)

        tracer = get_tracer()
        assert tracer is not None

    def test_init_creates_middleware(self):
        """Test that init() creates middleware."""
        init()

        # Should have created a global middleware
        assert prefactor_sdk._global_middleware is not None

    def test_init_multiple_times(self):
        """Test calling init() multiple times."""
        init()
        tracer1 = get_tracer()

        init()
        tracer2 = get_tracer()

        # Should return the same tracer instance
        assert tracer1 is tracer2

    def test_get_tracer_before_init(self):
        """Test getting tracer before initialization."""
        tracer = get_tracer()

        # Should auto-initialize and return a tracer
        assert tracer is not None


class TestGetTracer:
    """Test get_tracer() function."""

    def setup_method(self):
        """Reset global state before each test."""
        prefactor_sdk._global_tracer = None
        prefactor_sdk._global_handler = None
        prefactor_sdk._global_middleware = None

    def test_get_tracer_after_init(self):
        """Test getting tracer after initialization."""
        init()
        tracer = get_tracer()

        assert tracer is not None

    def test_get_tracer_returns_same_instance(self):
        """Test that get_tracer() returns the same instance."""
        init()

        tracer1 = get_tracer()
        tracer2 = get_tracer()

        assert tracer1 is tracer2
