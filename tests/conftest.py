"""Shared test fixtures for Confluence MCP server tests."""

import pytest


@pytest.fixture
def mock_settings():
    """Create mock settings for testing."""
    from unittest.mock import MagicMock

    settings = MagicMock()
    settings.confluence_url = "https://test.atlassian.net"
    settings.confluence_email = "test@example.com"
    settings.confluence_api_token = "test-token"
    settings.confluence_ssl_verify = True
    settings.confluence_allowed_hosts = ["*.atlassian.net"]
    settings.mcp_host = "127.0.0.1"
    settings.mcp_port = 5463
    settings.log_level = "INFO"
    settings.log_format = "console"
    settings.cache_enabled = False
    settings.rate_limit_per_second = 10.0
    settings.rate_limit_burst = 20
    settings.request_timeout = 30.0
    settings.upload_timeout = 120.0
    settings.base_url = "https://test.atlassian.net"
    settings.cache_partition_key = "test-partition-key"
    return settings
