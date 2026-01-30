"""Entry point for the Confluence MCP server.

This module is executed when running the package directly:
    python -m fast_mcp_confluence

Or via the installed script:
    fast-mcp-confluence
"""

import sys


def main() -> None:
    """Run the Confluence MCP server."""
    # Import settings first to validate configuration
    from .config import get_settings

    settings = get_settings()

    # Setup logging BEFORE importing anything else
    # This ensures all loggers are properly configured
    from .logging_config import get_logger, setup_logging

    setup_logging(
        level=settings.log_level,
        json_format=settings.log_format.lower() == "json",
    )

    logger = get_logger(__name__)

    # Log startup configuration (non-sensitive values only)
    logger.info(
        "Starting Confluence MCP server",
        extra={
            "confluence_url": settings.base_url,
            "host": settings.mcp_host,
            "port": settings.mcp_port,
            "cache_enabled": settings.cache_enabled,
            "log_level": settings.log_level,
            "log_format": settings.log_format,
            "auth_enabled": settings.mcp_api_key is not None,
        },
    )

    # Import server after logging is configured
    from .server import mcp

    try:
        # Run the server with HTTP transport
        mcp.run(
            transport="streamable-http",
            host=settings.mcp_host,
            port=settings.mcp_port,
        )
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
        sys.exit(0)
    except Exception:
        logger.exception("Server failed to start")
        sys.exit(1)


if __name__ == "__main__":
    main()
