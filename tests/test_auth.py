"""Tests for API key authentication."""

import pytest

from fast_mcp_confluence.auth import ApiKeyVerifier, AuthRateLimiter


class TestApiKeyVerifier:
    """Tests for API key verification."""

    @pytest.mark.asyncio
    async def test_valid_api_key(self):
        """Valid API key returns access token."""
        verifier = ApiKeyVerifier(api_key="secret-key-123")
        token = await verifier.verify_token("secret-key-123")

        assert token is not None
        assert token.client_id == "api-key-client"
        assert token.scopes == []

    @pytest.mark.asyncio
    async def test_invalid_api_key(self):
        """Invalid API key returns None."""
        verifier = ApiKeyVerifier(api_key="secret-key-123")
        token = await verifier.verify_token("wrong-key")

        assert token is None

    @pytest.mark.asyncio
    async def test_empty_key_rejected(self):
        """Empty key is rejected."""
        verifier = ApiKeyVerifier(api_key="secret-key-123")
        token = await verifier.verify_token("")

        assert token is None

    @pytest.mark.asyncio
    async def test_partial_key_rejected(self):
        """Partial key match is rejected."""
        verifier = ApiKeyVerifier(api_key="secret-key-123")
        token = await verifier.verify_token("secret-key")

        assert token is None

    @pytest.mark.asyncio
    async def test_key_with_extra_chars_rejected(self):
        """Key with extra characters is rejected."""
        verifier = ApiKeyVerifier(api_key="secret-key-123")
        token = await verifier.verify_token("secret-key-123-extra")

        assert token is None

    @pytest.mark.asyncio
    async def test_case_sensitive(self):
        """Key comparison is case-sensitive."""
        verifier = ApiKeyVerifier(api_key="Secret-Key-123")
        token = await verifier.verify_token("secret-key-123")

        assert token is None


class TestAuthRateLimiter:
    """Tests for authentication rate limiting."""

    @pytest.mark.asyncio
    async def test_allows_initial_requests(self):
        """Initial requests are allowed."""
        limiter = AuthRateLimiter(max_attempts=5, lockout_duration=60, window=300)

        for _ in range(4):
            assert await limiter.check_rate_limit() is True
            await limiter.record_failure()

    @pytest.mark.asyncio
    async def test_lockout_after_max_failures(self):
        """Lockout occurs after max failures."""
        limiter = AuthRateLimiter(max_attempts=3, lockout_duration=60, window=300)

        # Record max failures
        for _ in range(3):
            await limiter.check_rate_limit()
            await limiter.record_failure()

        # Should be locked out
        assert await limiter.check_rate_limit() is False

    @pytest.mark.asyncio
    async def test_success_clears_failures(self):
        """Successful auth clears failure count."""
        limiter = AuthRateLimiter(max_attempts=3, lockout_duration=60, window=300)

        # Record some failures
        await limiter.record_failure()
        await limiter.record_failure()

        # Success should clear
        await limiter.record_success()

        # Should still be allowed
        assert await limiter.check_rate_limit() is True
