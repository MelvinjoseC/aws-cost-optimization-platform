import logging
import os
import sys

def get_logger(name: str) -> logging.Logger:
    """
    Returns a configured logger with log level determined by environment.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S%z'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        # Default to INFO, but allow configuring via LOG_LEVEL
        log_level_str = os.environ.get("LOG_LEVEL", "INFO").upper()
        log_level = getattr(logging, log_level_str, logging.INFO)
        logger.setLevel(log_level)
        
    return logger
