"""Test basic imports for prefactor-core package."""


class TestBasicImports:
    """Test that all modules can be imported correctly."""

    def test_import_queue_base(self):
        """Test importing queue base module."""
        from prefactor_core.queue.base import Queue, QueueClosedError

        assert Queue is not None
        assert QueueClosedError is not None

    def test_import_queue_memory(self):
        """Test importing queue memory module."""
        from prefactor_core.queue.memory import InMemoryQueue

        assert InMemoryQueue is not None

    def test_import_queue_executor(self):
        """Test importing queue executor module."""
        from prefactor_core.queue.executor import TaskExecutor

        assert TaskExecutor is not None

    def test_import_queue(self):
        """Test importing queue package."""
        from prefactor_core.queue import (
            InMemoryQueue,
            Queue,
            QueueClosedError,
            TaskExecutor,
        )

        assert all([Queue, QueueClosedError, InMemoryQueue, TaskExecutor])

    def test_import_models(self):
        """Test importing models."""
        from prefactor_core.models import AgentInstance, Span

        assert AgentInstance is not None
        assert Span is not None

    def test_import_operations(self):
        """Test importing operations."""
        from prefactor_core.operations import Operation, OperationType

        assert Operation is not None
        assert OperationType is not None

    def test_import_exceptions(self):
        """Test importing exceptions."""
        from prefactor_core.exceptions import (
            ClientAlreadyInitializedError,
            ClientNotInitializedError,
            PrefactorCoreError,
        )

        assert PrefactorCoreError is not None
        assert ClientNotInitializedError is not None
        assert ClientAlreadyInitializedError is not None

    def test_import_config(self):
        """Test importing config."""
        from prefactor_core.config import PrefactorCoreConfig, QueueConfig

        assert PrefactorCoreConfig is not None
        assert QueueConfig is not None

    def test_import_context_stack(self):
        """Test importing context stack."""
        from prefactor_core.context_stack import SpanContextStack

        assert SpanContextStack is not None

    def test_import_main_package(self):
        """Test importing main package exports."""
        import prefactor_core

        # Check that all expected exports exist
        assert hasattr(prefactor_core, "PrefactorCoreClient")
        assert hasattr(prefactor_core, "PrefactorCoreConfig")
        assert hasattr(prefactor_core, "QueueConfig")
        assert hasattr(prefactor_core, "SpanContext")
        assert hasattr(prefactor_core, "SpanContextStack")
        assert hasattr(prefactor_core, "AgentInstance")
        assert hasattr(prefactor_core, "Span")
        assert hasattr(prefactor_core, "Operation")
        assert hasattr(prefactor_core, "OperationType")
        assert hasattr(prefactor_core, "Queue")
        assert hasattr(prefactor_core, "InMemoryQueue")
        assert hasattr(prefactor_core, "TaskExecutor")
