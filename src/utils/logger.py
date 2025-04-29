#!/usr/bin/env python3
"""
Logging utilities for the crawler.

This module provides a consistent logging setup across the application,
including both console and file output, with consistent formatting.

Usage:
    from src.utils.logger import setup_logger
    
    logger = setup_logger(__name__)
    logger.debug("Detailed information, typically of interest only when diagnosing problems")
    logger.info("Confirmation that things are working as expected")
    logger.warning("An indication that something unexpected happened")
    logger.error("Due to a more serious problem, the software has not been able to perform a function")
    logger.critical("A serious error, indicating that the program itself may be unable to continue running")
"""

import logging
import logging.handlers
import os
import sys
from datetime import datetime

from src.config.settings import (LOG_DATE_FORMAT, LOG_FORMAT_CONSOLE,
                                 LOG_FORMAT_FILE, LOG_LEVEL, LOGS_DIR)


class ContextAdapter(logging.LoggerAdapter):
    """
    Adapter that allows adding context to log messages.
    
    This adapter enhances log messages with contextual information
    like worker ID, URL, domain, etc.
    """
    
    def process(self, msg, kwargs):
        if 'extra' not in kwargs:
            kwargs['extra'] = self.extra
        else:
            kwargs['extra'].update(self.extra)
        return msg, kwargs


def setup_logger(name, log_level=None, context=None):
    """
    Set up a logger with console and file handlers.
    
    Args:
        name (str): Logger name, usually the module name (__name__)
        log_level (int): Logging level (optional, defaults to settings.LOG_LEVEL)
        context (dict): Contextual information to include in every log message
        
    Returns:
        logging.LoggerAdapter: Configured logger adapter with context
        
    Example:
        # Basic usage
        logger = setup_logger(__name__)
        logger.info("Starting process")
        
        # With context
        logger = setup_logger(__name__, context={"worker_id": "worker-123"})
        logger.info("Processing URL: %s", url)  # Will include worker_id in context
    """
    # Set log level from settings if not explicitly provided
    if log_level is None:
        log_level = getattr(logging, LOG_LEVEL)
        
    # Ensure logs directory exists
    os.makedirs(LOGS_DIR, exist_ok=True)
        
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    logger.propagate = False
    
    # Check if handlers already exist to avoid duplicate logs
    if logger.handlers:
        # If already set up but context provided, return adapter
        if context:
            return ContextAdapter(logger, context)
        return logger
    
    # Create formatters
    console_formatter = logging.Formatter(
        LOG_FORMAT_CONSOLE,
        datefmt=LOG_DATE_FORMAT
    )
    file_formatter = logging.Formatter(
        LOG_FORMAT_FILE
    )
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)
    
    # Create file handler
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"{today}.log"
    
    # Use rotating file handler to prevent large log files
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)
    
    # Add handlers to logger
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    # If context provided, return a logger adapter
    if context:
        return ContextAdapter(logger, context)
    
    return logger


def get_logger_with_context(base_logger, **context):
    """
    Get a new logger with additional context from an existing logger.
    
    Args:
        base_logger: The original logger or logger adapter
        **context: Keyword arguments for context to add
        
    Returns:
        logging.LoggerAdapter: Logger adapter with updated context
        
    Example:
        # Create a task-specific logger from the main logger
        task_logger = get_logger_with_context(logger, task_id="task-123", url="http://example.com")
        task_logger.info("Task started")  # Will include task_id and url in context
    """
    if isinstance(base_logger, ContextAdapter):
        # Merge new context with existing context
        new_context = {**base_logger.extra, **context}
        return ContextAdapter(base_logger.logger, new_context)
    else:
        # Create new adapter with context
        return ContextAdapter(base_logger, context) 
