"""Centralized logging configuration with structured output.

This module provides standardized logging across the application with support
for JSON-structured output suitable for production log aggregation systems.

Features:
- JSON-structured logging for production environments
- Request correlation ID tracking
- Performance timing decorators
- Consistent log format across all modules

Usage:
    from .logging_config import get_logger, timed

    logger = get_logger(__name__)
    logger.info("Processing request", extra={"page_id": "12345"})

    @timed
    async def slow_operation():
        ...
"""

import contextvars
import functools
import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

# Context variable for request correlation IDs
correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "correlation_id", default=None
)

T = TypeVar("T")

# Exact field names that should always be redacted
SENSITIVE_LOG_FIELDS_EXACT = {
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "encryption_key",
    "mcp_api_key",
    "confluence_api_token",
    "access_key",
    "secret_key",
    "private_key",
}

# Suffixes that indicate sensitive data (e.g., db_password, auth_token)
# Note: _key is intentionally excluded as it's too generic (space_key, cache_key)
SENSITIVE_LOG_SUFFIXES = ("_password", "_secret", "_token", "_credential")


def _sanitize_log_value(key: str, value: Any) -> Any:
    """Sanitize log values by redacting sensitive fields.

    Args:
        key: Field name (checked against sensitive patterns)
        value: Value to potentially redact

    Returns:
        Original value or "[REDACTED]" for sensitive fields
    """
    key_lower = key.lower()

    # Check exact matches first
    if key_lower in SENSITIVE_LOG_FIELDS_EXACT:
        return "[REDACTED]"

    # Check suffix patterns (e.g., db_password, auth_token)
    if key_lower.endswith(SENSITIVE_LOG_SUFFIXES):
        return "[REDACTED]"

    return value


class StructuredFormatter(logging.Formatter):
    """JSON-structured log formatter for production environments.

    Produces newline-delimited JSON logs suitable for log aggregation
    systems like ELK, Splunk, or CloudWatch.

    Output format:
        {"timestamp": "...", "level": "INFO", "logger": "...", "message": "...", ...}
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add correlation ID if present
        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_data["correlation_id"] = correlation_id

        # Add extra fields (excluding standard LogRecord attributes)
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "taskName",
            "message",
        }
        for key, value in record.__dict__.items():
            if key not in standard_attrs and not key.startswith("_"):
                # Sanitize sensitive fields before logging
                log_data[key] = _sanitize_log_value(key, value)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable console formatter for development.

    Produces colored, human-readable logs for development environments.
    """

    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record for console output."""
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Build base message
        message = f"{timestamp} {color}[{record.levelname:8}]{self.RESET} {record.name}: "
        message += record.getMessage()

        # Add correlation ID if present
        correlation_id = correlation_id_var.get()
        if correlation_id:
            message += f" [cid={correlation_id}]"

        # Add exception info if present
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)

        return message


def setup_logging(
    level: str = "INFO",
    json_format: bool = False,
    stream: Any = None,
) -> None:
    """Configure application-wide logging.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: If True, use JSON structured logging; otherwise console format.
        stream: Output stream (defaults to stderr for MCP compatibility).
    """
    if stream is None:
        stream = sys.stderr  # stdout reserved for MCP protocol

    # Get numeric level
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create and configure handler
    handler = logging.StreamHandler(stream)
    handler.setLevel(numeric_level)

    if json_format:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(ConsoleFormatter())

    root_logger.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with standard configuration.

    Args:
        name: Logger name (typically __name__).

    Returns:
        Configured logger instance.

    Example:
        logger = get_logger(__name__)
        logger.info("Processing page", extra={"page_id": "12345"})
    """
    return logging.getLogger(name)


def set_correlation_id(correlation_id: str | None) -> None:
    """Set the correlation ID for the current context.

    Args:
        correlation_id: Unique identifier for request tracing.
    """
    correlation_id_var.set(correlation_id)


def get_correlation_id() -> str | None:
    """Get the current correlation ID.

    Returns:
        Current correlation ID or None.
    """
    return correlation_id_var.get()


def timed(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to log execution time of functions.

    Works with both sync and async functions. Logs timing at DEBUG level.

    Args:
        func: Function to time.

    Returns:
        Wrapped function that logs execution time.

    Example:
        @timed
        async def fetch_pages():
            ...
    """
    logger = get_logger(func.__module__)

    @functools.wraps(func)
    async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            result = await func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "%s completed in %.2fms",
                func.__name__,
                elapsed_ms,
                extra={"timing_ms": elapsed_ms, "function": func.__name__},
            )
            return result
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "%s failed after %.2fms",
                func.__name__,
                elapsed_ms,
                extra={"timing_ms": elapsed_ms, "function": func.__name__},
            )
            raise

    @functools.wraps(func)
    def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "%s completed in %.2fms",
                func.__name__,
                elapsed_ms,
                extra={"timing_ms": elapsed_ms, "function": func.__name__},
            )
            return result
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "%s failed after %.2fms",
                func.__name__,
                elapsed_ms,
                extra={"timing_ms": elapsed_ms, "function": func.__name__},
            )
            raise

    # Return appropriate wrapper based on function type
    if asyncio_iscoroutinefunction(func):
        return async_wrapper  # type: ignore[return-value]
    return sync_wrapper  # type: ignore[return-value]


def asyncio_iscoroutinefunction(func: Callable[..., Any]) -> bool:
    """Check if function is an async coroutine function."""
    import asyncio

    return asyncio.iscoroutinefunction(func)
