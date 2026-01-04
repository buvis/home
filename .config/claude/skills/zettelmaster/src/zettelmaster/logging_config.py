#!/usr/bin/env python
"""
Centralized logging configuration for ZettelMaster.
Provides structured logging with rotation and multiple handlers.
"""

import logging
import logging.handlers
from pathlib import Path
from typing import Optional
import sys
import json
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record):
        log_obj = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage()
        }
        
        # Add extra fields if present
        if hasattr(record, 'zettel_id'):
            log_obj['zettel_id'] = record.zettel_id
        if hasattr(record, 'operation'):
            log_obj['operation'] = record.operation
        if hasattr(record, 'duration_ms'):
            log_obj['duration_ms'] = record.duration_ms
        if hasattr(record, 'error_type'):
            log_obj['error_type'] = record.error_type
        
        # Add exception info if present
        if record.exc_info:
            log_obj['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_obj)


class ColoredConsoleFormatter(logging.Formatter):
    """Colored console formatter for better readability."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def format(self, record):
        # Add color to level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
        
        # Format the message
        message = super().format(record)
        
        # Reset levelname for other handlers
        record.levelname = levelname
        
        return message


class ZettelLogger:
    """Custom logger wrapper with context management."""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.context = {}
    
    def set_context(self, **kwargs):
        """Set context that will be added to all log messages."""
        self.context.update(kwargs)
    
    def clear_context(self):
        """Clear the logging context."""
        self.context.clear()
    
    def _log_with_context(self, level, msg, *args, **kwargs):
        """Add context to log messages."""
        extra = kwargs.get('extra', {})
        extra.update(self.context)
        kwargs['extra'] = extra
        
        if level == 'debug':
            self.logger.debug(msg, *args, **kwargs)
        elif level == 'info':
            self.logger.info(msg, *args, **kwargs)
        elif level == 'warning':
            self.logger.warning(msg, *args, **kwargs)
        elif level == 'error':
            self.logger.error(msg, *args, **kwargs)
        elif level == 'critical':
            self.logger.critical(msg, *args, **kwargs)
    
    def debug(self, msg, *args, **kwargs):
        self._log_with_context('debug', msg, *args, **kwargs)
    
    def info(self, msg, *args, **kwargs):
        self._log_with_context('info', msg, *args, **kwargs)
    
    def warning(self, msg, *args, **kwargs):
        self._log_with_context('warning', msg, *args, **kwargs)
    
    def error(self, msg, *args, **kwargs):
        self._log_with_context('error', msg, *args, **kwargs)
    
    def critical(self, msg, *args, **kwargs):
        self._log_with_context('critical', msg, *args, **kwargs)
    
    def operation(self, operation: str, zettel_id: Optional[str] = None):
        """Log an operation with optional zettel ID."""
        extra = {'operation': operation}
        if zettel_id:
            extra['zettel_id'] = zettel_id
        self.info(f"Operation: {operation}", extra=extra)
    
    def validation_error(self, zettel_id: str, errors: list):
        """Log validation errors."""
        self.error(
            f"Validation failed for {zettel_id}: {len(errors)} errors",
            extra={'zettel_id': zettel_id, 'errors': errors}
        )
    
    def timing(self, operation: str, duration_ms: float):
        """Log operation timing."""
        self.info(
            f"{operation} completed in {duration_ms:.2f}ms",
            extra={'operation': operation, 'duration_ms': duration_ms}
        )


def setup_logging(
    log_dir: Optional[Path] = None,
    log_level: str = 'INFO',
    console_output: bool = True,
    file_output: bool = True,
    structured: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5
) -> None:
    """
    Configure logging for the entire application.
    
    Args:
        log_dir: Directory for log files (default: ./logs)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        console_output: Enable console logging
        file_output: Enable file logging
        structured: Use structured JSON logging for files
        max_bytes: Max size for log files before rotation
        backup_count: Number of backup files to keep
    """
    if log_dir is None:
        log_dir = Path('logs')
    
    # Create log directory if needed
    if file_output:
        log_dir.mkdir(exist_ok=True)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        
        # Use colored formatter for console
        console_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        console_handler.setFormatter(ColoredConsoleFormatter(console_format))
        
        root_logger.addHandler(console_handler)
    
    # File handler
    if file_output:
        # Main log file with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / 'zettelmaster.log',
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        file_handler.setLevel(getattr(logging, log_level.upper()))
        
        # Use structured or plain formatter
        if structured:
            file_handler.setFormatter(StructuredFormatter())
        else:
            file_format = '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
            file_handler.setFormatter(logging.Formatter(file_format))
        
        root_logger.addHandler(file_handler)
        
        # Error log file (errors and above only)
        error_handler = logging.handlers.RotatingFileHandler(
            log_dir / 'errors.log',
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        error_handler.setLevel(logging.ERROR)
        
        if structured:
            error_handler.setFormatter(StructuredFormatter())
        else:
            error_format = '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s\n%(exc_info)s'
            error_handler.setFormatter(logging.Formatter(error_format))
        
        root_logger.addHandler(error_handler)
    
    # Log initial setup
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: level={log_level}, console={console_output}, file={file_output}, structured={structured}")


def get_logger(name: str) -> ZettelLogger:
    """
    Get a logger instance with context management capabilities.
    
    Args:
        name: Logger name (typically __name__)
    
    Returns:
        ZettelLogger instance
    """
    return ZettelLogger(name)


# Configure default logging when module is imported
def init_default_logging():
    """Initialize with sensible defaults."""
    setup_logging(
        log_level='INFO',
        console_output=True,
        file_output=True,
        structured=False  # Use plain format by default for readability
    )


# Example usage
if __name__ == "__main__":
    # Setup logging
    setup_logging(
        log_level='DEBUG',
        structured=True
    )
    
    # Get logger
    logger = get_logger(__name__)
    
    # Basic logging
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    
    # With context
    logger.set_context(zettel_id="20251107143022", operation="validation")
    logger.info("Processing zettel")
    
    # Operation logging
    logger.operation("parse_zettel", zettel_id="20251107143022")
    
    # Timing
    import time
    start = time.time()
    time.sleep(0.1)
    duration = (time.time() - start) * 1000
    logger.timing("validation", duration)
    
    # Validation error
    logger.validation_error("20251107143022", ["Missing title", "Invalid date format"])
    
    # Clear context
    logger.clear_context()
    logger.info("Context cleared")