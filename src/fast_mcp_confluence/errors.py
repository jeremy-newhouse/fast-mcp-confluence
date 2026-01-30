"""Standardized error types and handling for Confluence MCP tools.

This module provides a consistent error handling strategy across all tools.
All errors are converted to a standardized response format that clients
can reliably parse and handle.

Error Codes:
    VALIDATION_ERROR: Input validation failed
    CONFLUENCE_API_ERROR: Confluence API returned an error
    CACHE_ERROR: Cache operation failed
    RATE_LIMIT_ERROR: Rate limit exceeded
    AUTHENTICATION_ERROR: Authentication failed
    PERMISSION_ERROR: Permission denied
    UNKNOWN_ERROR: Unexpected error occurred

Usage:
    from .errors import ValidationError, format_error_response

    try:
        validate_input(data)
    except ValidationError as e:
        return format_error_response(e)
"""

from typing import Any

from .logging_config import get_logger

logger = get_logger(__name__)


class ConfluenceToolError(Exception):
    """Base exception for all Confluence tool errors.

    All tool-specific errors inherit from this class, enabling consistent
    error handling and response formatting.

    Attributes:
        message: Human-readable error description.
        code: Machine-readable error code for programmatic handling.
        status_code: HTTP status code if applicable.
        field: Field name that caused the error (for validation errors).
        details: Additional error context.
    """

    def __init__(
        self,
        message: str,
        code: str = "UNKNOWN_ERROR",
        status_code: int | None = None,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        """Initialize Confluence tool error.

        Args:
            message: Human-readable error message.
            code: Error code (e.g., "VALIDATION_ERROR", "CONFLUENCE_API_ERROR").
            status_code: HTTP status code if from Confluence API.
            field: Field name for validation errors.
            details: Additional structured error information.
        """
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.field = field
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary representation.

        Returns:
            Dictionary with error details suitable for JSON serialization.
        """
        result: dict[str, Any] = {
            "message": self.message,
            "code": self.code,
        }
        if self.status_code is not None:
            result["status_code"] = self.status_code
        if self.field is not None:
            result["field"] = self.field
        if self.details:
            result["details"] = self.details
        return result


class ValidationError(ConfluenceToolError):
    """Input validation error.

    Raised when user input fails validation checks. Includes the
    field name and specific validation failure reason.

    Example:
        raise ValidationError(
            message="Page ID must be numeric",
            field="page_id",
            details={"provided": "abc", "expected": "numeric string"}
        )
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=400,
            field=field,
            details=details,
        )


class ConfluenceApiError(ConfluenceToolError):
    """Confluence API error.

    Raised when the Confluence API returns an error response. Contains
    the HTTP status code and any error details from Confluence.

    Example:
        raise ConfluenceApiError(
            message="Page not found",
            status_code=404,
            details={"page_id": "12345"}
        )
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="CONFLUENCE_API_ERROR",
            status_code=status_code,
            details=details,
        )


class CacheError(ConfluenceToolError):
    """Cache operation error.

    Raised when a cache operation fails. Cache errors are generally
    non-fatal and the operation should fall back to direct API access.

    Example:
        raise CacheError(
            message="Failed to read from cache database",
            details={"cache_key": "spaces:all"}
        )
    """

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="CACHE_ERROR",
            status_code=None,  # Cache errors are internal
            details=details,
        )


class RateLimitError(ConfluenceToolError):
    """Rate limit exceeded error.

    Raised when the Confluence API rate limit is exceeded. Includes
    retry information when available.

    Example:
        raise RateLimitError(
            message="Rate limit exceeded, retry after 60 seconds",
            details={"retry_after": 60}
        )
    """

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        error_details = details or {}
        if retry_after is not None:
            error_details["retry_after"] = retry_after
        super().__init__(
            message=message,
            code="RATE_LIMIT_ERROR",
            status_code=429,
            details=error_details,
        )


class AuthenticationError(ConfluenceToolError):
    """Authentication error.

    Raised when authentication fails, either for MCP endpoint
    or Confluence API authentication.

    Example:
        raise AuthenticationError(
            message="Invalid API key",
            details={"auth_type": "api_key"}
        )
    """

    def __init__(
        self,
        message: str = "Authentication failed",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            status_code=401,
            details=details,
        )


class PermissionError(ConfluenceToolError):
    """Permission denied error.

    Raised when the user lacks permission for an operation.

    Example:
        raise PermissionError(
            message="You do not have permission to edit this page",
            details={"page_id": "12345", "required_permission": "EDIT"}
        )
    """

    def __init__(
        self,
        message: str = "Permission denied",
        details: dict[str, Any] | None = None,
    ):
        super().__init__(
            message=message,
            code="PERMISSION_ERROR",
            status_code=403,
            details=details,
        )


def format_error_response(error: Exception) -> dict[str, Any]:
    """Convert any exception to a standardized error response.

    All tool functions should use this to ensure consistent error
    response format across the API.

    Args:
        error: Any exception (preferably a ConfluenceToolError subclass).

    Returns:
        Standardized error response dictionary:
        {
            "success": False,
            "error": {
                "message": "...",
                "code": "...",
                "status_code": 404,  # optional
                "field": "...",      # optional
                "details": {}        # optional
            }
        }

    Example:
        try:
            result = await some_operation()
            return {"success": True, "data": result}
        except Exception as e:
            return format_error_response(e)
    """
    if isinstance(error, ConfluenceToolError):
        return {
            "success": False,
            "error": error.to_dict(),
        }

    # Handle non-ConfluenceToolError exceptions
    # Security: Log the actual error server-side but return generic message
    # to prevent information disclosure (file paths, config values, etc.)
    logger.exception("Unexpected error occurred", extra={"error_type": type(error).__name__})
    return {
        "success": False,
        "error": {
            "message": "An unexpected error occurred",
            "code": "UNKNOWN_ERROR",
        },
    }


def format_success_response(
    data: Any,
    cached: bool = False,
    timing_ms: float | None = None,
) -> dict[str, Any]:
    """Create a standardized success response.

    Args:
        data: Response data (dict, list, or primitive).
        cached: Whether the response came from cache.
        timing_ms: Operation timing in milliseconds.

    Returns:
        Standardized success response dictionary:
        {
            "success": True,
            "data": {...},
            "_cached": False,
            "_timing_ms": 123.45
        }
    """
    response: dict[str, Any] = {
        "success": True,
        "data": data,
    }
    if cached:
        response["_cached"] = True
    if timing_ms is not None:
        response["_timing_ms"] = round(timing_ms, 2)
    return response
