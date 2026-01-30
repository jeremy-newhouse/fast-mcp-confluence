"""MCP tools for Confluence watcher operations.

Tools:
- get_page_watchers: Get watchers on a page
- add_page_watch: Add current user as watcher
- remove_page_watch: Remove current user as watcher

Note: Some watcher operations may use the v1 API as v2 support is limited.
"""

from typing import Annotated, Any

from pydantic import Field

from ..logging_config import get_logger
from ..server import confluence, mcp
from ..services.confluence_client import ConfluenceError
from ..utils.validation import (
    ValidationError,
    build_response,
    validate_page_id,
)

logger = get_logger(__name__)


@mcp.tool(description="Get watchers on a Confluence page.")
async def get_page_watchers(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
) -> dict[str, Any]:
    """Get all watchers on a page.

    Note: This uses the v1 API as v2 does not have a dedicated watchers endpoint.
    """
    try:
        page_id = validate_page_id(page_id)

        # V1 API endpoint for watchers
        result = await confluence.get_v1(f"/content/{page_id}/notification/child-created")

        watchers = []
        for watcher in result.get("results", []):
            watchers.append({
                "account_id": watcher.get("accountId"),
                "display_name": watcher.get("displayName"),
                "email": watcher.get("email"),
            })

        return build_response(
            True,
            page_id=page_id,
            total=len(watchers),
            watchers=watchers,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        # If the endpoint doesn't exist, provide helpful message
        if e.status_code == 404:
            return build_response(
                False,
                error="Watcher information not available for this page",
                status_code=e.status_code
            )
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting page watchers")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Add current user as a watcher on a Confluence page.")
async def add_page_watch(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
) -> dict[str, Any]:
    """Add the current authenticated user as a watcher on a page.

    Note: This uses the v1 API.
    """
    try:
        page_id = validate_page_id(page_id)

        # V1 API to add watch for current user
        await confluence.post_v1(
            f"/user/watch/content/{page_id}",
            body={}
        )

        return build_response(
            True,
            message=f"Now watching page {page_id}",
            page_id=page_id,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error adding page watch")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Remove current user as a watcher from a Confluence page.")
async def remove_page_watch(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
) -> dict[str, Any]:
    """Remove the current authenticated user as a watcher from a page.

    Note: This uses the v1 API.
    """
    try:
        page_id = validate_page_id(page_id)

        # V1 API to remove watch for current user
        await confluence.delete_v1(f"/user/watch/content/{page_id}")

        return build_response(
            True,
            message=f"Stopped watching page {page_id}",
            page_id=page_id,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error removing page watch")
        return build_response(False, error="Internal error occurred")
