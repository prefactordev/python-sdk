"""Tests for logging setup."""

import logging

from prefactor_core.utils.logging import configure_logging, get_logger


class TestConfigureLogging:
    """Test logging configuration."""

    def test_configure_logging_default(self, monkeypatch):
        """Test default logging level is WARNING."""
        monkeypatch.delenv("PREFACTOR_LOG_LEVEL", raising=False)
        logger = configure_logging()
        assert logger.level == logging.WARNING

    def test_configure_logging_debug(self, monkeypatch):
        """Test DEBUG logging level."""
        monkeypatch.setenv("PREFACTOR_LOG_LEVEL", "DEBUG")
        logger = configure_logging()
        assert logger.level == logging.DEBUG

    def test_configure_logging_info(self, monkeypatch):
        """Test INFO logging level."""
        monkeypatch.setenv("PREFACTOR_LOG_LEVEL", "INFO")
        logger = configure_logging()
        assert logger.level == logging.INFO

    def test_configure_logging_warning(self, monkeypatch):
        """Test WARNING logging level."""
        monkeypatch.setenv("PREFACTOR_LOG_LEVEL", "WARNING")
        logger = configure_logging()
        assert logger.level == logging.WARNING

    def test_configure_logging_error(self, monkeypatch):
        """Test ERROR logging level."""
        monkeypatch.setenv("PREFACTOR_LOG_LEVEL", "ERROR")
        logger = configure_logging()
        assert logger.level == logging.ERROR

    def test_configure_logging_invalid_level(self, monkeypatch):
        """Test invalid logging level defaults to WARNING."""
        monkeypatch.setenv("PREFACTOR_LOG_LEVEL", "INVALID")
        logger = configure_logging()
        assert logger.level == logging.WARNING

    def test_configure_logging_case_insensitive(self, monkeypatch):
        """Test logging level is case insensitive."""
        monkeypatch.setenv("PREFACTOR_LOG_LEVEL", "debug")
        logger = configure_logging()
        assert logger.level == logging.DEBUG


class TestGetLogger:
    """Test getting loggers."""

    def test_get_logger_name(self):
        """Test getting a logger with a specific name."""
        logger = get_logger("test_module")
        assert logger.name == "prefactor_core.test_module"

    def test_get_logger_returns_same_instance(self):
        """Test that get_logger returns the same instance."""
        logger1 = get_logger("test_module")
        logger2 = get_logger("test_module")
        assert logger1 is logger2
