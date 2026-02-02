"""Test basic imports for prefactor-next package."""

import pytest


class TestBasicImports:
    """Test that all modules can be imported correctly."""

    def test_import_queue_base(self):
        """Test importing queue base module."""
        from prefactor_next.queue.base import Queue, QueueClosedError

        assert Queue is not None
        assert QueueClosedError is not None

    def test_import_queue_memory(self):
        """Test importing queue memory module."""
        from prefactor_next.queue.memory import InMemoryQueue

        assert InMemoryQueue is not None

    def test_import_queue_executor(self):
        """Test importing queue executor module."""
        from prefactor_next.queue.executor import TaskExecutor

        assert TaskExecutor is not None

    def test_import_queue(self):
        """Test importing queue package."""
        from prefactor_next.queue import (
            Queue,
            QueueClosedError,
            InMemoryQueue,
            TaskExecutor,
        )

        assert all([Queue, QueueClosedError, InMemoryQueue, TaskExecutor])

    def test_import_models(self):
        """Test importing models."""
        from prefactor_next.models import AgentInstance, Span

        assert AgentInstance is not None
        assert Span is not None

    def test_import_operations(self):
        """Test importing operations."""
        from prefactor_next.operations import Operation, OperationType

        assert Operation is not None
        assert OperationType is not None

    def test_import_exceptions(self):
        """Test importing exceptions."""
        from prefactor_next.exceptions import (
            PrefactorNextError,
            ClientNotInitializedError,
            ClientAlreadyInitializedError,
        )

        assert PrefactorNextError is not None
        assert ClientNotInitializedError is not None
        assert ClientAlreadyInitializedError is not None

    def test_import_config(self):
        """Test importing config."""
        from prefactor_next.config import PrefactorNextConfig, QueueConfig

        assert PrefactorNextConfig is not None
        assert QueueConfig is not None

    def test_import_context_stack(self):
        """Test importing context stack."""
        from prefactor_next.context_stack import SpanContextStack

        assert SpanContextStack is not None

    def test_import_main_package(self):
        """Test importing main package exports."""
        import prefactor_next

        # Check that all expected exports exist
        assert hasattr(prefactor_next, "PrefactorNextClient")
        assert hasattr(prefactor_next, "PrefactorNextConfig")
        assert hasattr(prefactor_next, "QueueConfig")
        assert hasattr(prefactor_next, "SpanContext")
        assert hasattr(prefactor_next, "SpanContextStack")
        assert hasattr(prefactor_next, "AgentInstance")
        assert hasattr(prefactor_next, "Span")
        assert hasattr(prefactor_next, "Operation")
        assert hasattr(prefactor_next, "OperationType")
        assert hasattr(prefactor_next, "Queue")
        assert hasattr(prefactor_next, "InMemoryQueue")
        assert hasattr(prefactor_next, "TaskExecutor")
