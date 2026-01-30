"""MCP tools for Confluence space operations.

Tools:
- get_spaces: List all spaces
- get_space: Get space by ID
- get_space_by_key: Get space by key
- create_space: Create new space
- update_space: Update space details
- delete_space: Delete a space
"""

from typing import Annotated, Any

from pydantic import Field

from ..logging_config import get_logger
from ..server import cache, confluence, mcp
from ..services.cache import CacheService
from ..services.confluence_client import ConfluenceError
from ..utils.validation import (
    ValidationError,
    build_response,
    validate_page_id,
    validate_space_key,
)

logger = get_logger(__name__)


@mcp.tool(description="List all Confluence spaces with optional filtering.")
async def get_spaces(
    space_type: Annotated[
        str | None,
        Field(description="Filter by type: 'global' or 'personal'"),
    ] = None,
    status: Annotated[
        str | None,
        Field(description="Filter by status: 'current' or 'archived'"),
    ] = "current",
    limit: Annotated[
        int,
        Field(description="Maximum number of spaces to return", ge=1, le=250),
    ] = 25,
) -> dict[str, Any]:
    """List all Confluence spaces.

    Returns a list of spaces the user has access to, with optional filtering
    by type and status.
    """
    try:
        # Check cache first
        cache_key = CacheService.make_key("spaces", space_type or "all", status or "all", limit)
        if cache:
            cached = await cache.get(cache_key, "spaces")
            if cached:
                cached["_cached"] = True
                return cached

        # Build query parameters
        params: dict[str, Any] = {"limit": limit}
        if space_type:
            params["type"] = space_type
        if status:
            params["status"] = status

        result = await confluence.get_v2("/spaces", params=params)

        spaces = []
        for space in result.get("results", []):
            # Safely extract description - v2 API may return None or dict
            desc = space.get("description")
            description = ""
            if isinstance(desc, dict):
                plain = desc.get("plain")
                if isinstance(plain, dict):
                    description = plain.get("value", "")
            elif isinstance(desc, str):
                description = desc

            spaces.append({
                "id": space.get("id"),
                "key": space.get("key"),
                "name": space.get("name"),
                "type": space.get("type"),
                "status": space.get("status"),
                "description": description,
            })

        response = build_response(
            True,
            total=len(spaces),
            spaces=spaces,
        )

        # Cache the result
        if cache:
            await cache.set(cache_key, "spaces", response)

        return response

    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error listing spaces")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get a Confluence space by its ID.")
async def get_space(
    space_id: Annotated[str, Field(description="Space ID (numeric)")],
) -> dict[str, Any]:
    """Get detailed information about a specific space by ID."""
    try:
        space_id = validate_page_id(space_id)

        # Check cache
        cache_key = CacheService.make_key("space", space_id)
        if cache:
            cached = await cache.get(cache_key, "space")
            if cached:
                cached["_cached"] = True
                return cached

        result = await confluence.get_v2(f"/spaces/{space_id}")

        # Safely extract description
        desc = result.get("description")
        description = ""
        if isinstance(desc, dict):
            plain = desc.get("plain")
            if isinstance(plain, dict):
                description = plain.get("value", "")
        elif isinstance(desc, str):
            description = desc

        response = build_response(
            True,
            id=result.get("id"),
            key=result.get("key"),
            name=result.get("name"),
            type=result.get("type"),
            status=result.get("status"),
            description=description,
            homepage_id=result.get("homepageId"),
        )

        if cache:
            await cache.set(cache_key, "space", response)

        return response

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting space")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get a Confluence space by its key.")
async def get_space_by_key(
    space_key: Annotated[str, Field(description="Space key (e.g., MYSPACE)")],
) -> dict[str, Any]:
    """Get detailed information about a specific space by its key."""
    try:
        space_key = validate_space_key(space_key)

        # Check cache
        cache_key = CacheService.make_key("space", space_key)
        if cache:
            cached = await cache.get(cache_key, "space")
            if cached:
                cached["_cached"] = True
                return cached

        result = await confluence.get_v2("/spaces", params={"keys": space_key})

        spaces = result.get("results", [])
        if not spaces:
            return build_response(False, error=f"Space '{space_key}' not found")

        space = spaces[0]

        # Safely extract description
        desc = space.get("description")
        description = ""
        if isinstance(desc, dict):
            plain = desc.get("plain")
            if isinstance(plain, dict):
                description = plain.get("value", "")
        elif isinstance(desc, str):
            description = desc

        response = build_response(
            True,
            id=space.get("id"),
            key=space.get("key"),
            name=space.get("name"),
            type=space.get("type"),
            status=space.get("status"),
            description=description,
            homepage_id=space.get("homepageId"),
        )

        if cache:
            await cache.set(cache_key, "space", response)

        return response

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting space by key")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Create a new Confluence space.")
async def create_space(
    key: Annotated[str, Field(description="Space key (e.g., MYSPACE)")],
    name: Annotated[str, Field(description="Space name (display name)")],
    description: Annotated[
        str | None,
        Field(description="Space description (plain text)"),
    ] = None,
) -> dict[str, Any]:
    """Create a new Confluence space.

    Creates a global space with the specified key and name.
    """
    try:
        key = validate_space_key(key)

        # Use v1 API for space creation (more compatible)
        body: dict[str, Any] = {
            "key": key,
            "name": name,
        }

        if description:
            body["description"] = {
                "plain": {
                    "value": description,
                    "representation": "plain",
                }
            }

        result = await confluence.post_v1("/space", body=body)

        # Invalidate space cache
        if cache:
            await cache.invalidate(entity_type="spaces")

        return build_response(
            True,
            id=result.get("id"),
            key=result.get("key"),
            name=result.get("name"),
            type=result.get("type"),
            status=result.get("status"),
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error creating space")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Update a Confluence space's name or description.")
async def update_space(
    space_id: Annotated[str, Field(description="Space ID (numeric)")],
    name: Annotated[
        str | None,
        Field(description="New space name"),
    ] = None,
    description: Annotated[
        str | None,
        Field(description="New space description (plain text)"),
    ] = None,
) -> dict[str, Any]:
    """Update an existing Confluence space.

    Updates the space name and/or description.
    """
    try:
        space_id = validate_page_id(space_id)

        if not name and not description:
            return build_response(False, error="At least one of name or description is required")

        # First get the space key since v1 API uses key instead of ID
        space_result = await confluence.get_v2(f"/spaces/{space_id}")
        space_key = space_result.get("key")
        if not space_key:
            return build_response(False, error=f"Could not find space with ID {space_id}")

        # Use v1 API for space update (v2 doesn't support PUT for spaces)
        body: dict[str, Any] = {
            "key": space_key,
        }
        if name:
            body["name"] = name
        if description:
            body["description"] = {
                "plain": {
                    "value": description,
                    "representation": "plain",
                }
            }

        result = await confluence.put_v1(f"/space/{space_key}", body=body)

        # Invalidate cache
        if cache:
            await cache.invalidate(entity_type="spaces")
            await cache.invalidate(cache_key=CacheService.make_key("space", space_id))

        return build_response(
            True,
            id=result.get("id"),
            key=result.get("key"),
            name=result.get("name"),
            status=result.get("status"),
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error updating space")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Delete a Confluence space.")
async def delete_space(
    space_id: Annotated[str, Field(description="Space ID (numeric)")],
) -> dict[str, Any]:
    """Delete a Confluence space.

    Warning: This permanently deletes the space and all its content.
    """
    try:
        space_id = validate_page_id(space_id)

        # First get the space key since v1 API uses key instead of ID
        space_result = await confluence.get_v2(f"/spaces/{space_id}")
        space_key = space_result.get("key")
        if not space_key:
            return build_response(False, error=f"Could not find space with ID {space_id}")

        # Use v1 API for space deletion
        await confluence.delete_v1(f"/space/{space_key}")

        # Invalidate cache
        if cache:
            await cache.invalidate(entity_type="spaces")
            await cache.invalidate(cache_key=CacheService.make_key("space", space_id))

        return build_response(True, message=f"Space {space_id} deleted successfully")

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error deleting space")
        return build_response(False, error="Internal error occurred")
