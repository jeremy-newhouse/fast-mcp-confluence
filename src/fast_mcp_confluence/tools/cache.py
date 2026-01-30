"""MCP tools for cache management.

Tools:
- get_cache_stats: Get cache statistics
- invalidate_cache: Clear cache entries
"""

from typing import Annotated, Any

from pydantic import Field

from ..logging_config import get_logger
from ..server import cache, mcp
from ..services.cache import CacheCategory
from ..utils.validation import build_response

logger = get_logger(__name__)


@mcp.tool(description="Get cache statistics for the Confluence MCP server.")
async def get_cache_stats() -> dict[str, Any]:
    """Get statistics about the cache.

    Returns hit/miss counts and cache size information.
    """
    try:
        if not cache:
            return build_response(
                True,
                enabled=False,
                message="Cache is not enabled",
            )

        stats = await cache.get_stats()

        return build_response(
            True,
            enabled=True,
            hits=stats.get("hits", 0),
            misses=stats.get("misses", 0),
            total_entries=stats.get("total_entries", 0),
            db_size_bytes=stats.get("db_size_bytes"),
            categories=stats.get("categories", {}),
        )

    except Exception:
        logger.exception("Unexpected error getting cache stats")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Invalidate cache entries.")
async def invalidate_cache(
    category: Annotated[
        str | None,
        Field(
            description=(
                "Cache category to clear: 'spaces', 'metadata', 'users', 'labels', "
                "or None to clear all"
            )
        ),
    ] = None,
    key: Annotated[
        str | None,
        Field(description="Specific cache key to invalidate (optional)"),
    ] = None,
) -> dict[str, Any]:
    """Invalidate cache entries.

    Can clear:
    - All cache entries (no arguments)
    - All entries in a category (category only)
    - A specific key in a category (both category and key)
    """
    try:
        if not cache:
            return build_response(
                True,
                enabled=False,
                message="Cache is not enabled",
            )

        # Map string category to enum
        category_map = {
            "spaces": CacheCategory.SPACES,
            "metadata": CacheCategory.METADATA,
            "users": CacheCategory.USERS,
            "labels": CacheCategory.LABELS,
        }

        if category:
            category_lower = category.lower()
            if category_lower not in category_map:
                return build_response(
                    False,
                    error=f"Invalid category. Must be one of: {', '.join(category_map.keys())}",
                    field="category",
                )
            cache_category = category_map[category_lower]
        else:
            cache_category = None

        if key and not category:
            return build_response(
                False,
                error="Category is required when specifying a key",
                field="category",
            )

        # Perform invalidation
        if key and cache_category:
            # Invalidate specific key
            await cache.invalidate(key, cache_category)
            message = f"Invalidated cache key '{key}' in category '{category}'"
        elif cache_category:
            # Invalidate entire category
            await cache.invalidate_category(cache_category)
            message = f"Invalidated all entries in category '{category}'"
        else:
            # Clear all cache
            await cache.clear_all()
            message = "Cleared all cache entries"

        return build_response(
            True,
            message=message,
            category=category,
            key=key,
        )

    except Exception:
        logger.exception("Unexpected error invalidating cache")
        return build_response(False, error="Internal error occurred")
