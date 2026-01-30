"""MCP tools for Confluence metadata operations.

Tools:
- get_content_types: Get available content types (cached)
- search_users: Search for users
- get_current_user: Get current authenticated user
- get_space_permissions: Get space permission types

These tools use caching where appropriate to reduce API calls.
"""

from typing import Annotated, Any

from pydantic import Field

from ..logging_config import get_logger
from ..server import cache, confluence, mcp
from ..services.cache import CacheCategory
from ..services.confluence_client import ConfluenceError
from ..utils.validation import (
    ValidationError,
    build_response,
    validate_space_id,
)

logger = get_logger(__name__)


@mcp.tool(description="Get available Confluence content types.")
async def get_content_types() -> dict[str, Any]:
    """Get available content types in Confluence.

    This is typically a static list and is cached for 30 days.
    """
    try:
        cache_key = "content_types"

        # Check cache first
        if cache:
            cached = await cache.get(cache_key, CacheCategory.METADATA)
            if cached:
                cached["_cached"] = True
                return cached

        # V1 API provides more content type info
        result = await confluence.get_v1("/content/search", params={"cql": "type=page", "limit": 0})

        # Extract content types - this is a basic list as Confluence v2 doesn't have a dedicated endpoint
        content_types = [
            {"type": "page", "description": "Standard wiki page"},
            {"type": "blogpost", "description": "Blog post content"},
            {"type": "comment", "description": "Page or inline comment"},
            {"type": "attachment", "description": "File attachment"},
        ]

        response = build_response(
            True,
            content_types=content_types,
        )

        # Cache the result
        if cache:
            await cache.set(cache_key, CacheCategory.METADATA, response)

        return response

    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting content types")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Search for Confluence users.")
async def search_users(
    query: Annotated[
        str,
        Field(description="Search query (name)"),
    ],
    limit: Annotated[
        int,
        Field(description="Maximum number of users to return", ge=1, le=100),
    ] = 25,
) -> dict[str, Any]:
    """Search for users by name.

    Results are cached for a short period to reduce API load.
    Note: Email search is not supported by Confluence CQL.
    """
    try:
        if not query or len(query) < 2:
            return build_response(
                False,
                error="Search query must be at least 2 characters",
                field="query"
            )

        if len(query) > 255:
            return build_response(
                False,
                error="Search query exceeds maximum length of 255 characters",
                field="query"
            )

        # Block potentially dangerous characters in user search
        # These could be used for CQL injection in the fullname search
        dangerous_sequences = [';', '--', '/*', '*/']
        if any(seq in query for seq in dangerous_sequences):
            return build_response(
                False,
                error="Search query contains invalid characters",
                field="query"
            )

        cache_key = f"users_search:{query.lower()}:{limit}"

        # Check cache first (short TTL for user searches)
        if cache:
            cached = await cache.get(cache_key, CacheCategory.USERS)
            if cached:
                cached["_cached"] = True
                return cached

        # Escape double quotes to prevent CQL injection
        escaped_query = query.replace('"', '\\"')

        # Use v1 user search endpoint - only user.fullname is supported in CQL
        result = await confluence.get_v1(
            "/search/user",
            params={"cql": f"user.fullname~\"{escaped_query}\"", "limit": limit}
        )

        users = []
        for user in result.get("results", []):
            user_data = user.get("user", user)
            users.append({
                "account_id": user_data.get("accountId"),
                "display_name": user_data.get("displayName"),
                "email": user_data.get("email"),
                "account_type": user_data.get("accountType"),
            })

        response = build_response(
            True,
            query=query,
            total=len(users),
            users=users,
        )

        # Cache with short TTL
        if cache:
            await cache.set(cache_key, CacheCategory.USERS, response)

        return response

    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error searching users")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get the current authenticated Confluence user.")
async def get_current_user() -> dict[str, Any]:
    """Get information about the currently authenticated user."""
    try:
        cache_key = "current_user"

        # Check cache first
        if cache:
            cached = await cache.get(cache_key, CacheCategory.USERS)
            if cached:
                cached["_cached"] = True
                return cached

        result = await confluence.get_v1("/user/current")

        response = build_response(
            True,
            account_id=result.get("accountId"),
            display_name=result.get("displayName"),
            email=result.get("email"),
            account_type=result.get("accountType"),
        )

        # Cache the result
        if cache:
            await cache.set(cache_key, CacheCategory.USERS, response)

        return response

    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting current user")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get permission types for a Confluence space.")
async def get_space_permissions(
    space_id: Annotated[str, Field(description="Space ID (numeric)")],
) -> dict[str, Any]:
    """Get the permission types available for a space.

    Returns the permission structure for the space.
    """
    try:
        space_id = validate_space_id(space_id)

        cache_key = f"space_permissions:{space_id}"

        # Check cache first
        if cache:
            cached = await cache.get(cache_key, CacheCategory.METADATA)
            if cached:
                cached["_cached"] = True
                return cached

        result = await confluence.get_v2(f"/spaces/{space_id}/permissions")

        permissions = []
        for perm in result.get("results", []):
            permissions.append({
                "id": perm.get("id"),
                "principal": perm.get("principal"),
                "operation": perm.get("operation"),
            })

        response = build_response(
            True,
            space_id=space_id,
            total=len(permissions),
            permissions=permissions,
        )

        # Cache the result
        if cache:
            await cache.set(cache_key, CacheCategory.METADATA, response)

        return response

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting space permissions")
        return build_response(False, error="Internal error occurred")
