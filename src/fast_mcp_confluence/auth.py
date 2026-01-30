"""API key authentication for the MCP endpoint.

This module provides a simple API key authentication mechanism for the
FastMCP server. When MCP_API_KEY is configured, clients must provide
the key in the Authorization header as a Bearer token.

Security Features:
- Timing-safe comparison to prevent timing attacks
- Rate limiting on failed authentication attempts
- Optional: disabled when MCP_API_KEY is not set

Usage:
    Set MCP_API_KEY environment variable to enable authentication.
    Clients must include: Authorization: Bearer <api-key>
"""

import asyncio
import hmac
import logging
from time import monotonic

from fastmcp.server.auth import AccessToken, TokenVerifier

logger = logging.getLogger(__name__)

# Rate limiting constants for failed auth attempts
MAX_FAILED_ATTEMPTS = 5  # Max failures before lockout
LOCKOUT_DURATION = 60.0  # Seconds to lock out after max failures
ATTEMPT_WINDOW = 300.0  # Window in seconds to track failures


class AuthRateLimiter:
    """Rate limiter for failed authentication attempts.

    Tracks failed attempts and enforces a lockout period after too many failures.
    Uses a sliding window approach to gradually forget old failures.
    """

    def __init__(
        self,
        max_attempts: int = MAX_FAILED_ATTEMPTS,
        lockout_duration: float = LOCKOUT_DURATION,
        window: float = ATTEMPT_WINDOW,
    ):
        self.max_attempts = max_attempts
        self.lockout_duration = lockout_duration
        self.window = window
        self._failed_attempts: list[float] = []
        self._lockout_until: float = 0
        self._lock = asyncio.Lock()

    async def check_rate_limit(self) -> bool:
        """Check if requests are currently rate limited.

        Returns:
            True if requests should be allowed, False if rate limited.
        """
        async with self._lock:
            now = monotonic()

            # Check if still in lockout period
            if now < self._lockout_until:
                remaining = self._lockout_until - now
                logger.warning("Auth rate limited - lockout remaining: %.1fs", remaining)
                return False

            # Clean up old attempts outside the window
            self._failed_attempts = [t for t in self._failed_attempts if now - t < self.window]

            return True

    async def record_failure(self) -> None:
        """Record a failed authentication attempt."""
        async with self._lock:
            now = monotonic()
            self._failed_attempts.append(now)

            # Clean up old attempts
            self._failed_attempts = [t for t in self._failed_attempts if now - t < self.window]

            if len(self._failed_attempts) >= self.max_attempts:
                self._lockout_until = now + self.lockout_duration
                logger.warning(
                    "Auth rate limit triggered - too many failed attempts. Locked out for %.1fs",
                    self.lockout_duration,
                )

    async def record_success(self) -> None:
        """Record a successful authentication (clears failure count)."""
        async with self._lock:
            self._failed_attempts.clear()
            self._lockout_until = 0


class ApiKeyVerifier(TokenVerifier):
    """Simple API key verifier for MCP endpoint authentication.

    This verifier validates that the provided Bearer token matches the
    configured API key. Uses timing-safe comparison to prevent timing attacks
    and rate limiting to prevent brute-force attempts.

    Args:
        api_key: The API key that clients must provide.

    Example:
        >>> verifier = ApiKeyVerifier(api_key="secret-key-123")
        >>> # Clients must include: Authorization: Bearer secret-key-123
    """

    def __init__(self, api_key: str):
        """Initialize the API key verifier.

        Args:
            api_key: The API key that clients must provide for authentication.
        """
        super().__init__()
        self.api_key = api_key
        self._rate_limiter = AuthRateLimiter()

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify the provided token against the configured API key.

        Uses constant-time comparison to prevent timing attacks.
        Enforces rate limiting on failed attempts.

        Args:
            token: The bearer token from the Authorization header.

        Returns:
            AccessToken if the key matches, None otherwise.
        """
        # Check rate limit before attempting verification
        if not await self._rate_limiter.check_rate_limit():
            return None

        # Use constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(token, self.api_key):
            await self._rate_limiter.record_failure()
            return None

        # Clear failure count on success
        await self._rate_limiter.record_success()

        # Return a simple access token with no scopes
        return AccessToken(
            token=token,
            client_id="api-key-client",
            scopes=[],
            expires_at=None,
            claims={},
        )
