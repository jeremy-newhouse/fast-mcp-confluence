"""MCP tools for Confluence label operations.

Tools:
- get_page_labels: Get labels on a page
- add_page_labels: Add labels to a page
- remove_page_label: Remove a label from a page
- get_space_labels: Get labels in a space
"""

from typing import Annotated, Any

from pydantic import Field

from ..logging_config import get_logger
from ..server import confluence, mcp
from ..services.confluence_client import ConfluenceError
from ..utils.validation import (
    LabelInput,
    ValidationError,
    build_response,
    validate_page_id,
    validate_space_id,
)

logger = get_logger(__name__)


@mcp.tool(description="Get labels on a Confluence page.")
async def get_page_labels(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    limit: Annotated[
        int,
        Field(description="Maximum number of labels to return", ge=1, le=250),
    ] = 25,
) -> dict[str, Any]:
    """Get all labels on a page."""
    try:
        page_id = validate_page_id(page_id)

        result = await confluence.get_v2(
            f"/pages/{page_id}/labels",
            params={"limit": limit}
        )

        labels = []
        for label in result.get("results", []):
            labels.append({
                "id": label.get("id"),
                "name": label.get("name"),
                "prefix": label.get("prefix"),
            })

        return build_response(
            True,
            page_id=page_id,
            total=len(labels),
            labels=labels,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting page labels")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Add labels to a Confluence page.")
async def add_page_labels(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    labels: Annotated[
        list[str],
        Field(description="List of label names to add"),
    ],
) -> dict[str, Any]:
    """Add one or more labels to a page.

    Labels must be lowercase and contain only alphanumeric characters,
    underscores, or hyphens.
    """
    try:
        page_id = validate_page_id(page_id)

        if not labels:
            return build_response(False, error="At least one label is required", field="labels")

        # Validate each label
        validated_labels = []
        for label in labels:
            label_input = LabelInput(name=label)
            validated_labels.append(label_input.name)

        # Build request body - array of label objects for v1 API
        request_body = [{"prefix": "global", "name": name} for name in validated_labels]

        # Use v1 API - v2 doesn't support POST for labels
        result = await confluence.post_v1(
            f"/content/{page_id}/label",
            body=request_body
        )

        # Result is typically the list of added labels
        added = []
        if isinstance(result, list):
            for label in result:
                added.append({
                    "id": label.get("id"),
                    "name": label.get("name"),
                })
        elif isinstance(result, dict) and "results" in result:
            for label in result.get("results", []):
                added.append({
                    "id": label.get("id"),
                    "name": label.get("name"),
                })

        return build_response(
            True,
            page_id=page_id,
            added_count=len(added),
            labels=added,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ValueError as e:
        return build_response(False, error=str(e))
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error adding labels")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Remove a label from a Confluence page.")
async def remove_page_label(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    label: Annotated[str, Field(description="Label name to remove")],
) -> dict[str, Any]:
    """Remove a label from a page."""
    try:
        page_id = validate_page_id(page_id)

        # Validate label format
        label_input = LabelInput(name=label)

        # Use v1 API for label removal
        await confluence.delete_v1(f"/content/{page_id}/label/{label_input.name}")

        return build_response(
            True,
            message=f"Label '{label_input.name}' removed from page {page_id}",
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ValueError as e:
        return build_response(False, error=str(e))
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error removing label")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get labels in a Confluence space.")
async def get_space_labels(
    space_id: Annotated[str, Field(description="Space ID (numeric)")],
    limit: Annotated[
        int,
        Field(description="Maximum number of labels to return", ge=1, le=250),
    ] = 25,
) -> dict[str, Any]:
    """Get all labels used in a space."""
    try:
        space_id = validate_space_id(space_id)

        result = await confluence.get_v2(
            f"/spaces/{space_id}/labels",
            params={"limit": limit}
        )

        labels = []
        for label in result.get("results", []):
            labels.append({
                "id": label.get("id"),
                "name": label.get("name"),
                "prefix": label.get("prefix"),
            })

        return build_response(
            True,
            space_id=space_id,
            total=len(labels),
            labels=labels,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting space labels")
        return build_response(False, error="Internal error occurred")
