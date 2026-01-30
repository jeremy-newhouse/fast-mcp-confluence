"""MCP tools for Confluence comment operations.

Tools:
- add_footer_comment: Add a comment to a page
- get_footer_comments: Get comments on a page
- update_comment: Update an existing comment
- delete_comment: Delete a comment
- get_comment_versions: Get comment version history
"""

from typing import Annotated, Any

from pydantic import Field

from ..logging_config import get_logger
from ..server import confluence, mcp
from ..services.confluence_client import ConfluenceError
from ..utils.storage_format import markdown_to_storage, storage_to_markdown
from ..utils.validation import (
    ValidationError,
    build_response,
    validate_comment_body,
    validate_page_id,
)

logger = get_logger(__name__)


@mcp.tool(description="Add a footer comment to a Confluence page.")
async def add_footer_comment(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    body: Annotated[
        str,
        Field(description="Comment text in markdown format"),
    ],
) -> dict[str, Any]:
    """Add a footer comment to a page.

    The comment body supports markdown formatting.
    """
    try:
        page_id = validate_page_id(page_id)
        body = validate_comment_body(body)

        # Convert markdown to storage format
        storage_body = markdown_to_storage(body)

        # Use v1 API for creating comments
        request_body = {
            "type": "comment",
            "container": {"id": page_id, "type": "page"},
            "body": {
                "storage": {
                    "value": storage_body,
                    "representation": "storage",
                },
            },
        }

        result = await confluence.post_v1(f"/content", body=request_body)

        return build_response(
            True,
            comment_id=result.get("id"),
            page_id=page_id,
            version=result.get("version", {}).get("number"),
            created_at=result.get("createdAt"),
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error adding comment")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get footer comments on a Confluence page.")
async def get_footer_comments(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    limit: Annotated[
        int,
        Field(description="Maximum number of comments to return", ge=1, le=250),
    ] = 25,
) -> dict[str, Any]:
    """Get all footer comments on a page.

    Returns comments with body content converted to markdown.
    """
    try:
        page_id = validate_page_id(page_id)

        params = {
            "limit": limit,
            "body-format": "storage",
        }

        result = await confluence.get_v2(f"/pages/{page_id}/footer-comments", params=params)

        comments = []
        for comment in result.get("results", []):
            storage_body = comment.get("body", {}).get("storage", {}).get("value", "")
            comments.append({
                "id": comment.get("id"),
                "body": storage_to_markdown(storage_body),
                "version": comment.get("version", {}).get("number"),
                "created_at": comment.get("createdAt"),
                "author_id": comment.get("authorId"),
            })

        return build_response(
            True,
            page_id=page_id,
            total=len(comments),
            comments=comments,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting comments")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Update an existing Confluence comment.")
async def update_comment(
    comment_id: Annotated[str, Field(description="Comment ID (numeric)")],
    body: Annotated[
        str,
        Field(description="New comment text in markdown format"),
    ],
) -> dict[str, Any]:
    """Update an existing footer comment.

    Automatically increments the version number.
    """
    try:
        comment_id = validate_page_id(comment_id)  # Same numeric format
        body = validate_comment_body(body)

        # Get current comment to get version number using v1 API
        current = await confluence.get_v1(f"/content/{comment_id}")
        current_version = current.get("version", {}).get("number", 1)

        # Convert markdown to storage format
        storage_body = markdown_to_storage(body)

        # Use v1 API for updating comments
        request_body = {
            "type": "comment",
            "version": {
                "number": current_version + 1,
            },
            "body": {
                "storage": {
                    "value": storage_body,
                    "representation": "storage",
                },
            },
        }

        result = await confluence.put_v1(f"/content/{comment_id}", body=request_body)

        return build_response(
            True,
            comment_id=result.get("id"),
            version=result.get("version", {}).get("number"),
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error updating comment")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Delete a Confluence comment.")
async def delete_comment(
    comment_id: Annotated[str, Field(description="Comment ID (numeric)")],
) -> dict[str, Any]:
    """Delete a footer comment."""
    try:
        comment_id = validate_page_id(comment_id)

        # Use v1 API for comment deletion
        await confluence.delete_v1(f"/content/{comment_id}")

        return build_response(True, message=f"Comment {comment_id} deleted successfully")

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error deleting comment")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get version history of a Confluence comment.")
async def get_comment_versions(
    comment_id: Annotated[str, Field(description="Comment ID (numeric)")],
    limit: Annotated[
        int,
        Field(description="Maximum number of versions to return", ge=1, le=100),
    ] = 25,
) -> dict[str, Any]:
    """Get the version history of a comment."""
    try:
        comment_id = validate_page_id(comment_id)

        # Use v1 API for comment version history
        result = await confluence.get_v1(
            f"/content/{comment_id}/history",
            params={"expand": "lastUpdated,previousVersion"}
        )

        # v1 API returns history differently - extract versions
        versions = []
        # Get current version info
        if result.get("lastUpdated"):
            versions.append({
                "number": result.get("lastUpdated", {}).get("number"),
                "created_at": result.get("lastUpdated", {}).get("when"),
                "author_id": result.get("lastUpdated", {}).get("by", {}).get("accountId"),
            })

        return build_response(
            True,
            comment_id=comment_id,
            total=len(versions),
            versions=versions,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting comment versions")
        return build_response(False, error="Internal error occurred")
