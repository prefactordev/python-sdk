"""Configurable logging setup for Prefactor SDK."""

import logging
import os


def configure_logging() -> logging.Logger:
    """
    Configure logging for the Prefactor SDK.

    Reads the PREFACTOR_LOG_LEVEL environment variable to set the logging level.
    Valid values: DEBUG, INFO, WARNING, ERROR
    Default: WARNING

    Returns:
        The root logger for prefactor_sdk.
    """
    log_level_str = os.getenv("PREFACTOR_LOG_LEVEL", "WARNING").upper()

    # Map string to logging level
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }

    log_level = level_map.get(log_level_str, logging.WARNING)

    # Get the root logger for prefactor_core
    logger = logging.getLogger("prefactor_core")
    logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Create console handler
    handler = logging.StreamHandler()
    handler.setLevel(log_level)

    # Create formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for the specified module.

    Args:
        name: The module name (will be prefixed with 'prefactor_sdk.')

    Returns:
        A logger instance for the module.
    """
    return logging.getLogger(f"prefactor_core.{name}")
