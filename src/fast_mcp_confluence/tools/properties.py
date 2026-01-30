"""MCP tools for Confluence content property operations.

Tools:
- get_content_properties: Get all properties on a page
- get_content_property: Get a specific property
- set_content_property: Create or update a property
- delete_content_property: Delete a property
"""

import json
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


def _validate_property_key(key: str) -> str:
    """Validate a content property key."""
    if not key:
        raise ValidationError("Property key cannot be empty", field="key")
    if len(key) > 255:
        raise ValidationError("Property key exceeds 255 characters", field="key")
    # Keys should be alphanumeric with dots, hyphens, underscores
    if not all(c.isalnum() or c in ".-_" for c in key):
        raise ValidationError(
            "Property key must contain only alphanumeric characters, dots, hyphens, or underscores",
            field="key"
        )
    return key


@mcp.tool(description="Get all content properties on a Confluence page.")
async def get_content_properties(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    limit: Annotated[
        int,
        Field(description="Maximum number of properties to return", ge=1, le=250),
    ] = 25,
) -> dict[str, Any]:
    """Get all content properties on a page."""
    try:
        page_id = validate_page_id(page_id)

        result = await confluence.get_v2(
            f"/pages/{page_id}/properties",
            params={"limit": limit}
        )

        properties = []
        for prop in result.get("results", []):
            properties.append({
                "id": prop.get("id"),
                "key": prop.get("key"),
                "value": prop.get("value"),
                "version": prop.get("version", {}).get("number"),
            })

        return build_response(
            True,
            page_id=page_id,
            total=len(properties),
            properties=properties,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting content properties")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get a specific content property from a Confluence page.")
async def get_content_property(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    key: Annotated[str, Field(description="Property key")],
) -> dict[str, Any]:
    """Get a specific content property by key."""
    try:
        page_id = validate_page_id(page_id)
        key = _validate_property_key(key)

        # List all properties and filter by key (v2 API expects property ID, not key)
        result = await confluence.get_v2(
            f"/pages/{page_id}/properties",
            params={"limit": 250}
        )

        # Find property by key
        for prop in result.get("results", []):
            if prop.get("key") == key:
                return build_response(
                    True,
                    id=prop.get("id"),
                    key=prop.get("key"),
                    value=prop.get("value"),
                    version=prop.get("version", {}).get("number"),
                )

        return build_response(False, error=f"Property '{key}' not found on page {page_id}")

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting content property")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Create or update a content property on a Confluence page.")
async def set_content_property(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    key: Annotated[str, Field(description="Property key")],
    value: Annotated[
        str,
        Field(description="Property value (JSON string or plain string)"),
    ],
) -> dict[str, Any]:
    """Create or update a content property.

    The value can be a JSON object/array (as a string) or a plain string.
    If the property exists, it will be updated with an incremented version.
    """
    try:
        page_id = validate_page_id(page_id)
        key = _validate_property_key(key)

        # Try to parse value as JSON, otherwise use as string
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = value

        # List all properties to find existing one by key (v2 API uses ID, not key)
        existing_prop = None
        props_result = await confluence.get_v2(
            f"/pages/{page_id}/properties",
            params={"limit": 250}
        )
        for prop in props_result.get("results", []):
            if prop.get("key") == key:
                existing_prop = prop
                break

        if existing_prop:
            # Update existing property using its numeric ID
            prop_id = existing_prop.get("id")
            existing_version = existing_prop.get("version", {}).get("number", 1)
            request_body = {
                "key": key,
                "value": parsed_value,
                "version": {
                    "number": existing_version + 1,
                },
            }
            result = await confluence.put_v2(
                f"/pages/{page_id}/properties/{prop_id}",
                body=request_body
            )
        else:
            # Create new property
            request_body = {
                "key": key,
                "value": parsed_value,
            }
            result = await confluence.post_v2(
                f"/pages/{page_id}/properties",
                body=request_body
            )

        return build_response(
            True,
            id=result.get("id"),
            key=result.get("key"),
            value=result.get("value"),
            version=result.get("version", {}).get("number"),
            created=existing_prop is None,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error setting content property")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Delete a content property from a Confluence page.")
async def delete_content_property(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    key: Annotated[str, Field(description="Property key")],
) -> dict[str, Any]:
    """Delete a content property."""
    try:
        page_id = validate_page_id(page_id)
        key = _validate_property_key(key)

        # List all properties to find the one by key (v2 API uses ID, not key)
        props_result = await confluence.get_v2(
            f"/pages/{page_id}/properties",
            params={"limit": 250}
        )
        prop_id = None
        for prop in props_result.get("results", []):
            if prop.get("key") == key:
                prop_id = prop.get("id")
                break

        if not prop_id:
            return build_response(False, error=f"Property '{key}' not found on page {page_id}")

        await confluence.delete_v2(f"/pages/{page_id}/properties/{prop_id}")

        return build_response(
            True,
            message=f"Property '{key}' deleted from page {page_id}",
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error deleting content property")
        return build_response(False, error="Internal error occurred")
