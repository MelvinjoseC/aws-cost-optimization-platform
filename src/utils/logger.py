import logging
import os
import sys
from typing import Union


def get_logger(name: str) -> logging.Logger:
    """
    Retrieves or creates a configured logging.Logger instance.

    Configures the logger with a standardized format and stream handler
    directing logs to standard output if handlers are not already initialized.
    The logging level is resolved dynamically from the 'LOG_LEVEL' environment
    variable, defaulting to logging.INFO.

    Args:
        name (str): The name of the logger, typically __name__.

    Returns:
        logging.Logger: The configured Logger instance.
    """
    logger: logging.Logger = logging.getLogger(name)
    if not logger.handlers:
        handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
        formatter: logging.Formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Default to INFO, but allow configuring via LOG_LEVEL
        log_level_str: str = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level: int = int(getattr(logging, log_level_str, logging.INFO))
        logger.setLevel(log_level)

    return logger
