"""HTTP client for Confluence API requests.

This module provides an async HTTP client for communicating with Confluence Cloud API.
It handles authentication, rate limiting, and error handling.

Security Features:
- Rate limiting to prevent API abuse (token bucket algorithm)
- Error message sanitization to avoid leaking sensitive info
- Configurable SSL verification
- Configurable timeouts

Classes:
    RateLimiter: Token bucket rate limiter for API requests
    ConfluenceError: Exception for Confluence API errors
    ConfluenceClient: Main async HTTP client
"""

import asyncio
import base64
import logging
from time import monotonic
from typing import Any

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)

# Maximum error message length to prevent info leakage
MAX_ERROR_MESSAGE_LENGTH = 500

# Maximum response size to prevent DoS via large responses (50MB)
MAX_RESPONSE_SIZE = 50_000_000

# Maximum retries for rate-limited (429) responses
MAX_429_RETRIES = 3

# Maximum wait time for Retry-After header (2 minutes)
MAX_RETRY_AFTER_SECONDS = 120

# Fields that may contain sensitive data and should not be logged
SENSITIVE_PARAM_KEYS = {"cql", "body", "content", "password", "token", "secret", "key"}


def _sanitize_params_for_logging(params: dict | None) -> str:
    """Sanitize parameters for safe logging.

    Redacts values of sensitive keys to prevent information leakage.

    Args:
        params: Query parameters dict.

    Returns:
        String representation safe for logging.
    """
    if not params:
        return "{}"
    sanitized = {}
    for key, value in params.items():
        if key.lower() in SENSITIVE_PARAM_KEYS:
            sanitized[key] = "[REDACTED]"
        elif isinstance(value, str) and len(value) > 100:
            sanitized[key] = f"{value[:50]}...[truncated]"
        else:
            sanitized[key] = value
    return str(sanitized)


class RateLimiter:
    """Token bucket rate limiter for API requests.

    Prevents overwhelming the Confluence API with too many requests.
    Uses a token bucket algorithm that allows bursting while
    maintaining an average rate limit.

    Args:
        requests_per_second: Average rate limit (default: 10.0)
        burst: Maximum burst size (default: 20)

    Example:
        >>> limiter = RateLimiter(requests_per_second=10.0, burst=20)
        >>> await limiter.acquire()  # Blocks if rate limit exceeded
    """

    def __init__(self, requests_per_second: float = 10.0, burst: int = 20):
        """Initialize the rate limiter.

        Args:
            requests_per_second: Maximum average requests per second.
            burst: Maximum tokens available for burst traffic.
        """
        self.rate = requests_per_second
        self.burst = burst
        self._tokens = float(burst)
        self._last_update = monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a rate limit token, waiting if necessary.

        This method blocks until a token is available. Tokens are
        replenished at the configured rate.
        """
        async with self._lock:
            now = monotonic()
            elapsed = now - self._last_update
            # Replenish tokens based on elapsed time
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_update = now

            if self._tokens < 1:
                # Calculate wait time needed for one token
                wait_time = (1 - self._tokens) / self.rate
                logger.debug("Rate limit: waiting %.2fs", wait_time)
                await asyncio.sleep(wait_time)
                self._tokens = 0
            else:
                self._tokens -= 1


class ConfluenceError(Exception):
    """Exception raised for Confluence API errors.

    Contains the HTTP status code and sanitized error details
    from the Confluence API response.

    Attributes:
        status_code: HTTP status code from Confluence
        details: Additional error details (sanitized)
    """

    def __init__(self, message: str, status_code: int | None = None, details: Any = None):
        """Initialize Confluence error.

        Args:
            message: Human-readable error message (sanitized).
            status_code: HTTP status code if available.
            details: Additional error context (sanitized).
        """
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class ConfluenceClient:
    """Async HTTP client for Confluence Cloud API.

    Handles authentication, rate limiting, and error handling for
    all Confluence API requests. Uses httpx for async HTTP operations.

    Confluence API paths:
    - API v2: /wiki/api/v2/ (pages, spaces, etc.)
    - API v1: /wiki/rest/api/ (search, content)

    Security features:
    - Basic Auth with API token (credentials never logged)
    - Rate limiting to prevent API abuse
    - Error message sanitization
    - Configurable SSL verification and timeouts

    Args:
        settings: Application settings containing Confluence credentials.

    Example:
        >>> client = ConfluenceClient(settings)
        >>> result = await client.get_v2("/pages/12345")
        >>> await client.close()
    """

    def __init__(self, settings: Settings):
        """Initialize Confluence client.

        Args:
            settings: Settings object with Confluence URL, credentials,
                and configuration options.
        """
        self.settings = settings
        self._client: httpx.AsyncClient | None = None
        self._rate_limiter = RateLimiter(
            requests_per_second=settings.rate_limit_per_second,
            burst=settings.rate_limit_burst,
        )

    def _get_auth_header(self) -> str:
        """Generate Basic auth header value.

        Returns:
            Base64-encoded Authorization header value.
        """
        credentials = f"{self.settings.confluence_email}:{self.settings.confluence_api_token}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client.

        Creates a new client on first access. The client is configured
        with authentication headers, SSL settings, and timeouts.
        Base URL is set to {confluence_url}/wiki.

        Returns:
            Configured httpx.AsyncClient instance.
        """
        if self._client is None:
            # Security warning when SSL verification is disabled
            if not self.settings.confluence_ssl_verify:
                logger.warning(
                    "SSL verification DISABLED for Confluence connection. "
                    "This makes the connection vulnerable to man-in-the-middle attacks. "
                    "Only disable for development/testing with self-signed certificates."
                )

            base_url = f"{self.settings.base_url}/wiki"
            self._client = httpx.AsyncClient(
                base_url=base_url,
                headers={
                    "Authorization": self._get_auth_header(),
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                verify=self.settings.confluence_ssl_verify,
                timeout=self.settings.request_timeout,
            )
            logger.info(
                "Confluence client initialized for %s (SSL verify: %s)",
                base_url,
                self.settings.confluence_ssl_verify,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client and release resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("Confluence client closed")

    def _sanitize_error_message(self, message: str) -> str:
        """Sanitize error message to prevent information leakage.

        Args:
            message: Raw error message from Confluence.

        Returns:
            Truncated and sanitized error message.
        """
        if len(message) > MAX_ERROR_MESSAGE_LENGTH:
            message = message[: MAX_ERROR_MESSAGE_LENGTH - 3] + "..."
        return message

    def _handle_error(self, response: httpx.Response) -> None:
        """Handle error responses from Confluence.

        Extracts error information from Confluence's response format and
        raises a ConfluenceError with sanitized details.

        Args:
            response: HTTP response object with error status.

        Raises:
            ConfluenceError: Always raised with error details.
        """
        try:
            error_data = response.json()
        except Exception:
            error_data = {}

        # Extract error message from Confluence response format
        message = self._extract_error_message(error_data)

        # Sanitize and raise
        message = self._sanitize_error_message(message)
        raise ConfluenceError(
            message=f"Confluence API error ({response.status_code}): {message}",
            status_code=response.status_code,
            details=None,
        )

    def _extract_error_message(self, error_data: dict) -> str:
        """Extract error message from Confluence error response."""
        if not isinstance(error_data, dict):
            return "Request failed"

        # Confluence v2 API error format
        message = error_data.get("message")
        if message:
            return str(message)

        # Confluence v1 API error format
        if "errors" in error_data:
            errors = error_data.get("errors", [])
            if isinstance(errors, list) and errors:
                error_msgs = [e.get("message", str(e)) for e in errors if isinstance(e, dict)]
                if error_msgs:
                    return "; ".join(error_msgs)

        # Try title from error
        title = error_data.get("title")
        if title:
            return str(title)

        return "Unknown error"

    def _validate_response_size(self, response: httpx.Response) -> None:
        """Validate response size to prevent DoS via large responses.

        Args:
            response: HTTP response to validate.

        Raises:
            ConfluenceError: If response exceeds maximum allowed size.
        """
        content_length = len(response.content)
        if content_length > MAX_RESPONSE_SIZE:
            raise ConfluenceError(
                message=f"Response too large: {content_length} bytes "
                f"(max: {MAX_RESPONSE_SIZE} bytes)",
                status_code=response.status_code,
            )

    async def _handle_rate_limit(self, response: httpx.Response, attempt: int) -> bool:
        """Handle HTTP 429 rate limit response with retry.

        Args:
            response: HTTP response with 429 status.
            attempt: Current attempt number (0-indexed).

        Returns:
            True if should retry, False if max retries exceeded.
        """
        if response.status_code != 429:
            return False

        if attempt >= MAX_429_RETRIES - 1:
            logger.error(
                "Max retries exceeded for rate limit (429). Consider reducing request rate."
            )
            return False

        # Parse Retry-After header (seconds to wait)
        retry_after = response.headers.get("Retry-After", "60")
        try:
            wait_seconds = int(retry_after)
        except ValueError:
            wait_seconds = 60  # Default to 60 seconds

        # Cap wait time to prevent excessive delays
        wait_seconds = min(wait_seconds, MAX_RETRY_AFTER_SECONDS)

        logger.warning(
            "Rate limited by Confluence (429). Retrying in %d seconds (attempt %d/%d)",
            wait_seconds,
            attempt + 1,
            MAX_429_RETRIES,
        )
        await asyncio.sleep(wait_seconds)
        return True

    async def get_v2(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """Make a GET request to Confluence API v2.

        Args:
            path: API endpoint path (e.g., /pages/12345).
            params: Optional query parameters.

        Returns:
            Parsed JSON response as dict or list.

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        return await self.get(f"/api/v2{path}", params=params)

    async def get_v1(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """Make a GET request to Confluence API v1 (REST API).

        Used for search and some legacy endpoints.

        Args:
            path: API endpoint path (e.g., /content/search).
            params: Optional query parameters.

        Returns:
            Parsed JSON response as dict or list.

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        return await self.get(f"/rest/api{path}", params=params)

    async def get(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any] | list[Any]:
        """Make a GET request to Confluence API.

        Args:
            path: Full API endpoint path.
            params: Optional query parameters.

        Returns:
            Parsed JSON response as dict or list.

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        response: httpx.Response | None = None
        for attempt in range(MAX_429_RETRIES):
            await self._rate_limiter.acquire()
            logger.debug("GET %s params=%s", path, _sanitize_params_for_logging(params))
            response = await self.client.get(path, params=params)

            if await self._handle_rate_limit(response, attempt):
                continue

            if not response.is_success:
                self._handle_error(response)

            self._validate_response_size(response)
            return response.json() if response.content else {}

        # If we get here, all retries were exhausted on 429
        if response is not None:
            self._handle_error(response)
        return {}

    async def post_v2(
        self,
        path: str,
        body: dict[str, Any] | list[Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request to Confluence API v2.

        Args:
            path: API endpoint path.
            body: JSON request body.
            params: Optional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        return await self.post(f"/api/v2{path}", body=body, params=params)

    async def post_v1(
        self,
        path: str,
        body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request to Confluence API v1 (REST API).

        Used for watchers and some legacy endpoints.

        Args:
            path: API endpoint path.
            body: JSON request body.
            params: Optional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        return await self.post(f"/rest/api{path}", body=body, params=params)

    async def post(
        self,
        path: str,
        body: dict[str, Any] | list[Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request to Confluence API.

        Args:
            path: Full API endpoint path.
            body: JSON request body (dict or list).
            params: Optional query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        response: httpx.Response | None = None
        for attempt in range(MAX_429_RETRIES):
            await self._rate_limiter.acquire()
            logger.debug("POST %s", path)
            response = await self.client.post(path, json=body, params=params)

            if await self._handle_rate_limit(response, attempt):
                continue

            if not response.is_success:
                self._handle_error(response)

            self._validate_response_size(response)
            return response.json() if response.content else {}

        if response is not None:
            self._handle_error(response)
        return {}

    async def put_v2(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a PUT request to Confluence API v2.

        Args:
            path: API endpoint path.
            body: JSON request body.

        Returns:
            Parsed JSON response.

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        return await self.put(f"/api/v2{path}", body=body)

    async def put_v1(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a PUT request to Confluence API v1 (REST API).

        Used for content updates and some legacy endpoints.

        Args:
            path: API endpoint path.
            body: JSON request body.

        Returns:
            Parsed JSON response.

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        return await self.put(f"/rest/api{path}", body=body)

    async def put(self, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a PUT request to Confluence API.

        Args:
            path: Full API endpoint path.
            body: JSON request body.

        Returns:
            Parsed JSON response.

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        response: httpx.Response | None = None
        for attempt in range(MAX_429_RETRIES):
            await self._rate_limiter.acquire()
            logger.debug("PUT %s", path)
            response = await self.client.put(path, json=body)

            if await self._handle_rate_limit(response, attempt):
                continue

            if not response.is_success:
                self._handle_error(response)

            self._validate_response_size(response)
            return response.json() if response.content else {}

        if response is not None:
            self._handle_error(response)
        return {}

    async def delete_v2(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a DELETE request to Confluence API v2.

        Args:
            path: API endpoint path.
            params: Optional query parameters.

        Returns:
            Parsed JSON response (often empty).

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        return await self.delete(f"/api/v2{path}", params=params)

    async def delete_v1(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a DELETE request to Confluence API v1 (REST API).

        Used for watchers and some legacy endpoints.

        Args:
            path: API endpoint path.
            params: Optional query parameters.

        Returns:
            Parsed JSON response (often empty).

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        return await self.delete(f"/rest/api{path}", params=params)

    async def delete(
        self, path: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make a DELETE request to Confluence API.

        Args:
            path: Full API endpoint path.
            params: Optional query parameters.

        Returns:
            Parsed JSON response (often empty).

        Raises:
            ConfluenceError: If the request fails or response is too large.
        """
        response: httpx.Response | None = None
        for attempt in range(MAX_429_RETRIES):
            await self._rate_limiter.acquire()
            logger.debug("DELETE %s", path)
            response = await self.client.delete(path, params=params)

            if await self._handle_rate_limit(response, attempt):
                continue

            if not response.is_success:
                self._handle_error(response)

            self._validate_response_size(response)
            return response.json() if response.content else {}

        if response is not None:
            self._handle_error(response)
        return {}

    async def post_multipart(
        self,
        path: str,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """Make a multipart POST request for file uploads.

        Creates a separate client for multipart uploads to handle
        the different content-type requirements.

        Args:
            path: API endpoint path for attachment upload.
            filename: Name of the file being uploaded.
            content: Raw file content bytes.
            content_type: MIME type of the file.

        Returns:
            Parsed JSON response with attachment details.

        Raises:
            ConfluenceError: If the upload fails or response is too large.
        """
        files = {"file": (filename, content, content_type)}
        # Need to override content-type header for multipart
        headers = {
            "Authorization": self._get_auth_header(),
            "Accept": "application/json",
            "X-Atlassian-Token": "no-check",  # Required for attachment uploads
        }

        response: httpx.Response | None = None
        base_url = f"{self.settings.base_url}/wiki"
        for attempt in range(MAX_429_RETRIES):
            await self._rate_limiter.acquire()
            logger.debug("POST multipart %s filename=%s size=%d", path, filename, len(content))

            async with httpx.AsyncClient(
                base_url=base_url,
                verify=self.settings.confluence_ssl_verify,
                timeout=self.settings.upload_timeout,
            ) as client:
                response = await client.post(path, files=files, headers=headers)

            if await self._handle_rate_limit(response, attempt):
                continue

            if not response.is_success:
                self._handle_error(response)

            self._validate_response_size(response)
            return response.json() if response.content else {}

        if response is not None:
            self._handle_error(response)
        return {}
