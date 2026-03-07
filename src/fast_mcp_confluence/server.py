"""FastMCP server instance for Confluence.

This module initializes the FastMCP server with all services and tools.
It provides global instances of the Confluence client, cache service,
and the MCP server itself.

Usage:
    from .server import mcp, confluence, cache

    @mcp.tool(description="My tool")
    async def my_tool():
        result = await confluence.get_v2("/pages/123")
        return {"success": True, "data": result}
"""

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastmcp import FastMCP

from .auth import ApiKeyVerifier
from .config import get_settings
from .logging_config import get_logger
from .services.cache import CacheService
from .services.confluence_client import ConfluenceClient

logger = get_logger(__name__)

# Global settings instance
settings = get_settings()

# Global Confluence client instance
confluence = ConfluenceClient(settings)

# Global cache instance (if enabled)
cache: CacheService | None = None
if settings.cache_enabled:
    cache = CacheService(settings)

# Auth provider (if MCP_API_KEY is configured and auth is enabled)
auth_provider: ApiKeyVerifier | None = None
if settings.mcp_api_key and settings.mcp_auth_enabled:
    auth_provider = ApiKeyVerifier(api_key=settings.mcp_api_key)
    logger.info("MCP endpoint authentication enabled")
elif not settings.mcp_auth_enabled:
    logger.warning("MCP_AUTH_ENABLED=false - endpoint is UNAUTHENTICATED")
else:
    logger.warning(
        "MCP_API_KEY not set - endpoint is UNAUTHENTICATED. "
        "Set MCP_API_KEY environment variable to enable authentication."
    )


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Manage server lifecycle - initialize and cleanup services.

    Args:
        server: The FastMCP server instance.

    Yields:
        Empty context dict (services accessed via globals).
    """
    import time

    start_time = time.perf_counter()
    logger.info("Starting Confluence MCP server...")

    # Initialize cache if enabled
    if cache:
        await cache.initialize()
        logger.info("Cache service initialized")

    logger.info(
        "Server startup complete",
        extra={"startup_time_ms": round((time.perf_counter() - start_time) * 1000, 2)},
    )

    try:
        yield {}
    finally:
        # Shutdown
        shutdown_start = time.perf_counter()
        logger.info("Shutting down Confluence MCP server...")

        # Close cache
        if cache:
            await cache.close()
            logger.info("Cache service closed")

        # Close Confluence client
        await confluence.close()
        logger.info("Confluence client closed")

        logger.info(
            "Server shutdown complete",
            extra={"shutdown_time_ms": round((time.perf_counter() - shutdown_start) * 1000, 2)},
        )


# Create FastMCP server instance
mcp = FastMCP(
    name="Confluence MCP Server",
    instructions="""
This MCP server provides tools for interacting with Atlassian Confluence Cloud.

Key concepts:
- **Spaces** contain pages organized in hierarchies
- **Pages** have versions, labels, comments, and attachments
- Content uses markdown input (automatically converted to Confluence format)
- Use **CQL** (Confluence Query Language) for advanced searches

Common operations:
- Create/read/update/delete pages
- Search pages with CQL queries
- Manage page hierarchy (parent-child relationships)
- Work with labels, comments, and attachments

CQL Examples:
- `type=page AND space=MYSPACE` - All pages in a space
- `title~"meeting notes"` - Pages with title containing "meeting notes"
- `label=important` - Pages with the "important" label
- `created>=now("-7d")` - Pages created in the last 7 days
""",
    auth=auth_provider,
    lifespan=app_lifespan,
)


# Import all tool modules to register them with the server
# This must happen after mcp is created
def _register_tools() -> None:
    """Import tool modules to register them with the server.

    Tools are registered via decorators when modules are imported.
    """
    from . import tools  # noqa: F401

    # Import each tool module
    from .tools import attachments  # noqa: F401
    from .tools import bulk  # noqa: F401
    from .tools import cache as cache_tools  # noqa: F401
    from .tools import comments  # noqa: F401
    from .tools import labels  # noqa: F401
    from .tools import metadata  # noqa: F401
    from .tools import pages  # noqa: F401
    from .tools import properties  # noqa: F401
    from .tools import spaces  # noqa: F401
    from .tools import watchers  # noqa: F401


_register_tools()
