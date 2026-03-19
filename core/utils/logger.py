"""
Aethvion Suite - Logger
Structured logging with automatic Trace_ID injection
"""

import logging
import logging.config
import yaml
import os
from pathlib import Path
from typing import Optional
from .trace_manager import get_current_trace_id
from core.utils.paths import LOGS_SYSTEM


class TraceIDFilter(logging.Filter):
    """
    Logging filter that injects the current Trace_ID into log records.
    """
    
    def filter(self, record):
        """Add trace_id to the log record."""
        trace_id = get_current_trace_id()
        record.trace_id = trace_id if trace_id else "NO-TRACE"
        return True


class AethvionLogger:
    """
    Centralized logging system for Aethvion Suite.
    Automatically injects Trace_IDs and manages log lifecycle.
    """
    
    _initialized = False
    _loggers = {}
    
    @classmethod
    def initialize(cls, config_path: Optional[str] = None):
        """
        Initialize the logging system from configuration.
        
        Args:
            config_path: Path to logging.yaml, defaults to config/logging.yaml
        """
        if cls._initialized:
            return
        
        # Default config path
        if config_path is None:
            workspace = Path(__file__).parent.parent
            config_path = workspace / "config" / "logging.yaml"
        
        # Load configuration
        if not os.path.exists(config_path):
            # Fallback to basic configuration
            logging.basicConfig(
                level=logging.INFO,
                format='[%(asctime)s] [%(levelname)s] [Trace:%(trace_id)s] %(name)s - %(message)s'
            )
            print(f"Warning: Logging config not found at {config_path}, using basic config")
            cls._initialized = True
            return
        
        # Ensure log directory exists at project root
        log_dir = LOGS_SYSTEM
        log_dir.mkdir(parents=True, exist_ok=True)
        
        # Load YAML configuration
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Configure logging from YAML
        logging_config = config.get('logging', {})
        
        # Add TraceID filter to all handlers
        trace_filter = TraceIDFilter()
        
        # Set up basic logging first
        logging.basicConfig(level=logging.INFO)
        root_logger = logging.getLogger()
        
        # Add filter to all handlers
        for handler in root_logger.handlers:
            handler.addFilter(trace_filter)
        
        cls._initialized = True
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        Get a logger instance with Trace_ID support.
        
        Args:
            name: Logger name (typically module name)
            
        Returns:
            Configured logger instance
        """
        if not cls._initialized:
            cls.initialize()
        
        if name in cls._loggers:
            return cls._loggers[name]
        
        logger = logging.getLogger(name)
        
        # Add Trace_ID filter
        trace_filter = TraceIDFilter()
        for handler in logger.handlers:
            handler.addFilter(trace_filter)
        
        # If no handlers, add to root logger's handlers
        if not logger.handlers:
            for handler in logging.getLogger().handlers:
                if not any(isinstance(f, TraceIDFilter) for f in handler.filters):
                    handler.addFilter(trace_filter)
        
        cls._loggers[name] = logger
        return logger


def get_logger(name: str) -> logging.Logger:
    """
    Convenience function to get a logger.
    
    Args:
        name: Logger name (use __name__ in modules)
        
    Returns:
        Configured logger with Trace_ID support
    """
    return AethvionLogger.get_logger(name)


# Initialize logging system on import
AethvionLogger.initialize()
