"""Configuration settings for the Fast MCP Confluence server.

This module provides configuration management using pydantic-settings.
Settings are loaded from environment variables and .env files.

Environment Variables:
    CONFLUENCE_URL: Confluence instance URL (required)
    CONFLUENCE_EMAIL: User email for authentication (required)
    CONFLUENCE_API_TOKEN: API token for authentication (required)
    CONFLUENCE_SSL_VERIFY: Enable SSL verification (default: true)
    MCP_HOST: Server bind address (default: 127.0.0.1)
    MCP_PORT: Server port (default: 5463)
    LOG_LEVEL: Logging level (default: INFO)
    LOG_FORMAT: Log format - "console" or "json" (default: console)
    REQUEST_TIMEOUT: HTTP request timeout in seconds (default: 30.0)
    UPLOAD_TIMEOUT: File upload timeout in seconds (default: 120.0)
    RATE_LIMIT_PER_SECOND: API rate limit (default: 10.0)
    RATE_LIMIT_BURST: Rate limit burst size (default: 20)
    MCP_API_KEY: API key for MCP endpoint authentication (optional)

Cache Settings:
    CACHE_ENABLED: Enable SQLite caching (default: true)
    CACHE_DB_PATH: Path to cache database (default: ~/.fast-mcp-confluence/cache.db)
    CACHE_TTL_SPACES: TTL for spaces in seconds (default: 2592000 = 30 days)
    CACHE_TTL_METADATA: TTL for metadata in seconds (default: 2592000 = 30 days)
    CACHE_TTL_USERS: TTL for user data in seconds (default: 604800 = 7 days)
    CACHE_TTL_LABELS: TTL for labels in seconds (default: 86400 = 1 day)
    CACHE_CLEANUP_INTERVAL: Cleanup interval in seconds (default: 86400 = daily)
    CACHE_MAX_ENTRIES: Maximum cache entries (default: 10000)

Cache Encryption Settings:
    CACHE_ENCRYPTION_ENABLED: Enable SQLite encryption (default: false)
    CACHE_ENCRYPTION_KEY: Encryption key (min 32 chars, use openssl rand -hex 32)
    CACHE_ENCRYPTION_KEY_FILE: Path to file containing encryption key

Bulk Operation Settings:
    BULK_MAX_BATCH_SIZE: Maximum pages per bulk operation (default: 50)
    BULK_CONCURRENT_REQUESTS: Concurrent requests for bulk ops (default: 10)
"""

import hashlib
import ipaddress
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_private_or_internal_ip(hostname: str) -> bool:
    """Check if hostname is a private, loopback, or link-local IP.

    This prevents SSRF attacks by blocking requests to internal networks.

    Args:
        hostname: The hostname or IP address to check.

    Returns:
        True if the hostname is a private/internal IP, False otherwise.
    """
    if not hostname:
        return False
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
    except ValueError:
        # Not a valid IP address - likely a hostname, which is OK
        return False


def _is_allowed_hostname(hostname: str, allowed_patterns: list[str]) -> bool:
    """Check if hostname matches any allowed pattern.

    Supports glob-style patterns with * wildcard for subdomain matching.

    Args:
        hostname: The hostname to check.
        allowed_patterns: List of allowed patterns (e.g., ["*.atlassian.net"]).

    Returns:
        True if hostname matches any pattern, False otherwise.
    """
    import fnmatch

    if not hostname or not allowed_patterns:
        return False

    hostname_lower = hostname.lower()
    for pattern in allowed_patterns:
        if fnmatch.fnmatch(hostname_lower, pattern.lower()):
            return True
    return False


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    All settings can be configured via environment variables or a .env file.
    Required settings will raise an error if not provided.

    Attributes:
        confluence_url: Confluence Cloud instance URL.
        confluence_email: Email address for Confluence authentication.
        confluence_api_token: API token for Confluence authentication.
        confluence_ssl_verify: Whether to verify SSL certificates.
        mcp_host: Server bind address.
        mcp_port: Server port number.
        log_level: Python logging level.
        log_format: Log format - "console" or "json".
        request_timeout: HTTP request timeout in seconds.
        upload_timeout: File upload timeout in seconds.
        rate_limit_per_second: Maximum requests per second.
        rate_limit_burst: Maximum burst requests.
        mcp_api_key: API key for MCP endpoint authentication.
        cache_enabled: Whether SQLite caching is enabled.
        cache_db_path: Path to cache database file.
        cache_ttl_spaces: TTL for space data.
        cache_ttl_metadata: TTL for metadata (content types).
        cache_ttl_users: TTL for user search results.
        cache_ttl_labels: TTL for label data.
        cache_cleanup_interval: Background cleanup interval.
        cache_max_entries: Maximum cache entries before cleanup.
        bulk_max_batch_size: Maximum pages per bulk operation.
        bulk_concurrent_requests: Concurrent requests for bulk ops.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required Confluence configuration
    confluence_url: str
    confluence_email: str
    confluence_api_token: str

    # Optional SSL configuration
    confluence_ssl_verify: bool = True

    # SSRF protection: allowed hostname patterns (glob-style with * wildcard)
    # Set to empty list to disable hostname validation (not recommended)
    confluence_allowed_hosts: list[str] = ["*.atlassian.net"]

    # Server configuration
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 5463  # CONF on phone keypad

    # Logging
    log_level: str = "INFO"
    log_format: str = "console"  # "console" or "json"

    # HTTP client timeouts (in seconds)
    request_timeout: float = 30.0
    upload_timeout: float = 120.0  # Larger for attachment uploads

    # Rate limiting configuration
    rate_limit_per_second: float = 10.0
    rate_limit_burst: int = 20

    # MCP endpoint authentication (optional)
    # If set, clients must provide this key in the Authorization header
    mcp_api_key: str | None = None
    mcp_auth_enabled: bool = True

    # Cache configuration
    cache_enabled: bool = True
    cache_db_path: str = "~/.fast-mcp-confluence/cache.db"
    cache_ttl_spaces: int = 2592000  # 30 days - spaces rarely change
    cache_ttl_metadata: int = 2592000  # 30 days - content types, permissions
    cache_ttl_users: int = 604800  # 7 days - user search results (shorter for privacy)
    cache_ttl_labels: int = 86400  # 1 day - labels change more frequently
    cache_cleanup_interval: int = 86400  # Run cleanup daily
    cache_max_entries: int = 10000  # Maximum cache entries

    # Cache encryption (optional - requires sqlcipher3-binary)
    cache_encryption_enabled: bool = False
    cache_encryption_key: str | None = None
    cache_encryption_key_file: str | None = None

    # Bulk operation configuration
    bulk_max_batch_size: int = 50  # Maximum pages per bulk operation
    bulk_concurrent_requests: int = 10  # Concurrent requests for bulk ops

    # Graceful shutdown configuration
    graceful_shutdown_timeout: int = 30  # Seconds to wait for graceful shutdown

    @property
    def cache_db_full_path(self) -> Path:
        """Get expanded cache database path."""
        path = Path(os.path.expanduser(self.cache_db_path))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def base_url(self) -> str:
        """Get the full Confluence base URL.

        Security: Validates that the URL does not point to private/internal
        IP addresses and matches allowed hostname patterns to prevent SSRF attacks.

        Raises:
            ValueError: If the URL points to a private/internal IP or
                       doesn't match allowed hostname patterns.
        """
        url = self.confluence_url.strip()

        # Add https:// if no protocol specified
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        # Add .atlassian.net if it looks like just a site name (no dots in domain)
        if "." not in url.split("://", 1)[1]:
            url = f"{url}.atlassian.net"

        # SSRF Prevention: Block private/internal IP addresses
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if _is_private_or_internal_ip(hostname):
            raise ValueError(
                f"Confluence URL points to private/internal IP address: {hostname}. "
                "This is blocked for security reasons (SSRF prevention)."
            )

        # SSRF Prevention: Validate hostname against allowlist
        if self.confluence_allowed_hosts and not _is_allowed_hostname(
            hostname, self.confluence_allowed_hosts
        ):
            raise ValueError(
                f"Confluence hostname '{hostname}' is not in the allowed hosts list. "
                f"Allowed patterns: {self.confluence_allowed_hosts}. "
                "Set CONFLUENCE_ALLOWED_HOSTS to include this host or use '*.atlassian.net'."
            )

        return url.rstrip("/")

    @property
    def cache_partition_key(self) -> str:
        """Get cache partition key for isolating cache per user.

        Combines Confluence URL with MCP API Key (if set) to ensure:
        - Different Confluence instances have separate caches
        - Different users (API keys) have separate caches
        - Same user's cache persists across sessions

        Returns:
            A stable hash string identifying this user's cache partition.
        """
        # Include Confluence URL for instance isolation
        key_parts = [self.base_url]

        # Include MCP API Key for user isolation (if configured)
        if self.mcp_api_key:
            key_parts.append(self.mcp_api_key)
        else:
            # Fall back to Confluence credentials for user isolation
            key_parts.append(self.confluence_email)

        combined = ":".join(key_parts)
        # Use 32 hex chars (128-bit) for adequate collision resistance
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    @property
    def cache_encryption_key_resolved(self) -> str | None:
        """Resolve cache encryption key from env var or file.

        Priority:
        1. CACHE_ENCRYPTION_KEY environment variable (direct key)
        2. CACHE_ENCRYPTION_KEY_FILE (path to file containing key)

        Returns:
            The encryption key if encryption is enabled, None otherwise.

        Raises:
            ValueError: If encryption is enabled but no valid key is provided,
                or if the key is too short (< 32 characters).
            FileNotFoundError: If the key file doesn't exist.
            PermissionError: If the key file has insecure permissions.
        """
        if not self.cache_encryption_enabled:
            return None

        # Priority 1: Direct environment variable
        if self.cache_encryption_key:
            if len(self.cache_encryption_key) < 32:
                raise ValueError(
                    "Cache encryption key must be at least 32 characters. "
                    "Generate with: openssl rand -hex 32"
                )
            return self.cache_encryption_key

        # Priority 2: Key file
        if self.cache_encryption_key_file:
            key_path = Path(os.path.expanduser(self.cache_encryption_key_file))
            if not key_path.exists():
                raise FileNotFoundError(f"Cache encryption key file not found: {key_path}")

            # Security: Verify restrictive permissions (owner read/write only)
            stat = key_path.stat()
            if stat.st_mode & 0o077:  # Check if group/other have any permissions
                raise PermissionError(
                    f"Encryption key file has insecure permissions: {oct(stat.st_mode)}. "
                    "Must be 0o600 (owner read/write only). Fix with: chmod 600 <file>"
                )

            key = key_path.read_text().strip()
            if len(key) < 32:
                raise ValueError("Cache encryption key from file must be at least 32 characters")
            return key

        raise ValueError(
            "Cache encryption enabled but no key provided. "
            "Set CACHE_ENCRYPTION_KEY or CACHE_ENCRYPTION_KEY_FILE"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
