"""MCP tools for Confluence page operations.

Tools:
- create_page: Create a new page
- get_page: Get page by ID
- get_page_by_title: Get page by space key and title
- update_page: Update page content
- delete_page: Delete a page
- archive_page: Archive a page
- unarchive_page: Restore an archived page
- get_page_children: Get child pages
- move_page: Move page to new parent
- get_page_versions: Get version history
- search_pages: Search pages using CQL
"""

from typing import Annotated, Any

from pydantic import Field

from ..logging_config import get_logger
from ..server import cache, confluence, mcp
from ..services.cache import CacheService
from ..services.confluence_client import ConfluenceError
from ..utils.storage_format import markdown_to_storage, storage_to_markdown
from ..utils.validation import (
    ValidationError,
    build_response,
    validate_cql,
    validate_page_id,
    validate_page_title,
    validate_space_key,
)

logger = get_logger(__name__)


@mcp.tool(description="Create a new Confluence page with markdown content.")
async def create_page(
    space_key: Annotated[str, Field(description="Space key (e.g., MYSPACE)")],
    title: Annotated[str, Field(description="Page title (max 255 chars)")],
    body: Annotated[
        str,
        Field(
            description="Page content in markdown. Supports: **bold**, *italic*, "
            "# headings, - lists, ```code blocks```, [links](url), ![images](url)"
        ),
    ],
    parent_id: Annotated[
        str | None,
        Field(description="Parent page ID for hierarchy (optional)"),
    ] = None,
) -> dict[str, Any]:
    """Create a new page with markdown content.

    The markdown content is automatically converted to Confluence storage format.
    """
    try:
        space_key = validate_space_key(space_key)
        title = validate_page_title(title)

        # Verify space exists
        spaces_result = await confluence.get_v2("/spaces", params={"keys": space_key})
        spaces = spaces_result.get("results", [])
        if not spaces:
            return build_response(False, error=f"Space '{space_key}' not found")

        # Convert markdown to storage format
        storage_body = markdown_to_storage(body)

        # Build request body for v1 API (more compatible)
        request_body: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": storage_body,
                    "representation": "storage",
                },
            },
        }

        if parent_id:
            parent_id = validate_page_id(parent_id)
            request_body["ancestors"] = [{"id": parent_id}]

        # Use v1 API for page creation (better compatibility)
        result = await confluence.post_v1("/content", body=request_body)

        return build_response(
            True,
            page_id=result.get("id"),
            title=result.get("title"),
            space_key=space_key,
            version=result.get("version", {}).get("number"),
            status=result.get("status"),
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error creating page")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get a Confluence page by its ID.")
async def get_page(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    include_body: Annotated[
        bool,
        Field(description="Include page body content (as markdown)"),
    ] = True,
) -> dict[str, Any]:
    """Get detailed information about a page.

    The page body is converted from storage format to markdown for readability.
    """
    try:
        page_id = validate_page_id(page_id)

        params: dict[str, Any] = {}
        if include_body:
            params["body-format"] = "storage"

        result = await confluence.get_v2(f"/pages/{page_id}", params=params)

        page_data: dict[str, Any] = {
            "id": result.get("id"),
            "title": result.get("title"),
            "status": result.get("status"),
            "space_id": result.get("spaceId"),
            "parent_id": result.get("parentId"),
            "version": result.get("version", {}).get("number"),
            "created_at": result.get("createdAt"),
            "author_id": result.get("authorId"),
        }

        if include_body and "body" in result:
            storage_content = result.get("body", {}).get("storage", {}).get("value", "")
            page_data["body"] = storage_to_markdown(storage_content)

        return build_response(True, page=page_data)

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting page")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get a Confluence page by space key and title.")
async def get_page_by_title(
    space_key: Annotated[str, Field(description="Space key (e.g., MYSPACE)")],
    title: Annotated[str, Field(description="Page title (exact match)")],
    include_body: Annotated[
        bool,
        Field(description="Include page body content (as markdown)"),
    ] = True,
) -> dict[str, Any]:
    """Get a page by its space key and title.

    Useful when you know the page title but not the page ID.
    """
    try:
        space_key = validate_space_key(space_key)

        # Get space ID
        spaces_result = await confluence.get_v2("/spaces", params={"keys": space_key})
        spaces = spaces_result.get("results", [])
        if not spaces:
            return build_response(False, error=f"Space '{space_key}' not found")
        space_id = spaces[0]["id"]

        # Search for page by title in space
        params: dict[str, Any] = {"title": title}
        if include_body:
            params["body-format"] = "storage"

        result = await confluence.get_v2(f"/spaces/{space_id}/pages", params=params)

        pages = result.get("results", [])
        if not pages:
            return build_response(False, error=f"Page '{title}' not found in space '{space_key}'")

        page = pages[0]
        page_data: dict[str, Any] = {
            "id": page.get("id"),
            "title": page.get("title"),
            "status": page.get("status"),
            "space_id": page.get("spaceId"),
            "parent_id": page.get("parentId"),
            "version": page.get("version", {}).get("number"),
        }

        if include_body and "body" in page:
            storage_content = page.get("body", {}).get("storage", {}).get("value", "")
            page_data["body"] = storage_to_markdown(storage_content)

        return build_response(True, page=page_data)

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting page by title")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Update a Confluence page's title or content.")
async def update_page(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    title: Annotated[
        str | None,
        Field(description="New page title"),
    ] = None,
    body: Annotated[
        str | None,
        Field(description="New page content in markdown"),
    ] = None,
    version_message: Annotated[
        str | None,
        Field(description="Version comment describing the changes"),
    ] = None,
) -> dict[str, Any]:
    """Update an existing page.

    Updates the title and/or body. Automatically increments the version number.
    """
    try:
        page_id = validate_page_id(page_id)

        if not title and not body:
            return build_response(False, error="At least one of title or body is required")

        # Get current page to get version number
        current = await confluence.get_v2(f"/pages/{page_id}")
        current_version = current.get("version", {}).get("number", 1)
        current_title = current.get("title")
        current_status = current.get("status")

        # Build update body
        update_body: dict[str, Any] = {
            "id": page_id,
            "status": current_status,
            "title": title if title else current_title,
            "version": {
                "number": current_version + 1,
            },
        }

        if version_message:
            update_body["version"]["message"] = version_message

        if body:
            if title:
                validate_page_title(title)
            storage_body = markdown_to_storage(body)
            update_body["body"] = {
                "representation": "storage",
                "value": storage_body,
            }

        result = await confluence.put_v2(f"/pages/{page_id}", body=update_body)

        return build_response(
            True,
            page_id=result.get("id"),
            title=result.get("title"),
            version=result.get("version", {}).get("number"),
            status=result.get("status"),
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error updating page")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Delete a Confluence page.")
async def delete_page(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    purge: Annotated[
        bool,
        Field(description="Permanently delete instead of moving to trash"),
    ] = False,
) -> dict[str, Any]:
    """Delete a Confluence page.

    By default, moves the page to trash. Use purge=True to permanently delete.
    """
    try:
        page_id = validate_page_id(page_id)

        params: dict[str, Any] = {}
        if purge:
            params["status"] = "trashed"

        # Use v1 API for page deletion (v2 returns 404)
        await confluence.delete_v1(f"/content/{page_id}", params=params)

        return build_response(
            True,
            message=f"Page {page_id} {'permanently deleted' if purge else 'moved to trash'}"
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error deleting page")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Archive a Confluence page.")
async def archive_page(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
) -> dict[str, Any]:
    """Archive a Confluence page.

    Archived pages are hidden from normal views but can be restored later.
    This is a non-destructive alternative to deletion.
    """
    try:
        page_id = validate_page_id(page_id)

        # Get current page info
        current = await confluence.get_v2(f"/pages/{page_id}")
        current_version = current.get("version", {}).get("number", 1)
        current_title = current.get("title")
        current_status = current.get("status")

        if current_status == "archived":
            return build_response(False, error=f"Page {page_id} is already archived")

        # Update page status to archived
        update_body: dict[str, Any] = {
            "id": page_id,
            "status": "archived",
            "title": current_title,
            "version": {
                "number": current_version + 1,
                "message": "Page archived",
            },
        }

        result = await confluence.put_v2(f"/pages/{page_id}", body=update_body)

        return build_response(
            True,
            page_id=result.get("id"),
            title=result.get("title"),
            status=result.get("status"),
            version=result.get("version", {}).get("number"),
            message=f"Page {page_id} archived successfully",
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error archiving page")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Restore an archived Confluence page.")
async def unarchive_page(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
) -> dict[str, Any]:
    """Restore an archived Confluence page.

    Changes the page status from 'archived' back to 'current'.
    """
    try:
        page_id = validate_page_id(page_id)

        # Get current page info - need to specify status to find archived pages
        current = await confluence.get_v2(f"/pages/{page_id}", params={"status": "archived"})
        current_version = current.get("version", {}).get("number", 1)
        current_title = current.get("title")
        current_status = current.get("status")

        if current_status != "archived":
            return build_response(False, error=f"Page {page_id} is not archived (status: {current_status})")

        # Update page status to current
        update_body: dict[str, Any] = {
            "id": page_id,
            "status": "current",
            "title": current_title,
            "version": {
                "number": current_version + 1,
                "message": "Page restored from archive",
            },
        }

        result = await confluence.put_v2(f"/pages/{page_id}", body=update_body)

        return build_response(
            True,
            page_id=result.get("id"),
            title=result.get("title"),
            status=result.get("status"),
            version=result.get("version", {}).get("number"),
            message=f"Page {page_id} restored from archive",
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error unarchiving page")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get child pages of a Confluence page.")
async def get_page_children(
    page_id: Annotated[str, Field(description="Parent page ID (numeric)")],
    limit: Annotated[
        int,
        Field(description="Maximum number of children to return", ge=1, le=250),
    ] = 25,
) -> dict[str, Any]:
    """Get all direct child pages of a page."""
    try:
        page_id = validate_page_id(page_id)

        result = await confluence.get_v2(f"/pages/{page_id}/children", params={"limit": limit})

        children = []
        for child in result.get("results", []):
            children.append({
                "id": child.get("id"),
                "title": child.get("title"),
                "status": child.get("status"),
                "parent_id": child.get("parentId"),
            })

        return build_response(
            True,
            parent_id=page_id,
            total=len(children),
            children=children,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting page children")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Move a Confluence page to a new parent.")
async def move_page(
    page_id: Annotated[str, Field(description="Page ID to move (numeric)")],
    new_parent_id: Annotated[str, Field(description="New parent page ID (numeric)")],
) -> dict[str, Any]:
    """Move a page to be a child of another page."""
    try:
        page_id = validate_page_id(page_id)
        new_parent_id = validate_page_id(new_parent_id)

        # Get current page info
        current = await confluence.get_v2(f"/pages/{page_id}")
        current_version = current.get("version", {}).get("number", 1)
        current_title = current.get("title")
        current_status = current.get("status")

        # Update with new parent
        update_body: dict[str, Any] = {
            "id": page_id,
            "status": current_status,
            "title": current_title,
            "parentId": new_parent_id,
            "version": {
                "number": current_version + 1,
                "message": f"Moved to new parent {new_parent_id}",
            },
        }

        result = await confluence.put_v2(f"/pages/{page_id}", body=update_body)

        return build_response(
            True,
            page_id=result.get("id"),
            title=result.get("title"),
            new_parent_id=new_parent_id,
            version=result.get("version", {}).get("number"),
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error moving page")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get version history of a Confluence page.")
async def get_page_versions(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    limit: Annotated[
        int,
        Field(description="Maximum number of versions to return", ge=1, le=100),
    ] = 25,
) -> dict[str, Any]:
    """Get the version history of a page."""
    try:
        page_id = validate_page_id(page_id)

        result = await confluence.get_v2(f"/pages/{page_id}/versions", params={"limit": limit})

        versions = []
        for version in result.get("results", []):
            versions.append({
                "number": version.get("number"),
                "message": version.get("message"),
                "created_at": version.get("createdAt"),
                "author_id": version.get("authorId"),
            })

        return build_response(
            True,
            page_id=page_id,
            total=len(versions),
            versions=versions,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting page versions")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Search for Confluence pages using CQL (Confluence Query Language).")
async def search_pages(
    cql: Annotated[
        str,
        Field(
            description="CQL query string. Examples: "
            "'type=page AND space=MYSPACE', "
            "'title~\"meeting notes\"', "
            "'label=important AND created>=now(\"-7d\")'"
        ),
    ],
    limit: Annotated[
        int,
        Field(description="Maximum results to return", ge=1, le=100),
    ] = 25,
    include_body: Annotated[
        bool,
        Field(description="Include page body in results (slower)"),
    ] = False,
) -> dict[str, Any]:
    """Search for pages using CQL (Confluence Query Language).

    Common CQL operators:
    - type=page: Search only pages
    - space=KEY: Search in specific space
    - title~"text": Title contains text
    - text~"text": Content contains text
    - label=name: Pages with specific label
    - created>=now("-7d"): Created in last 7 days
    - ancestor=page_id: Under specific parent
    """
    try:
        cql = validate_cql(cql)

        # Ensure we're searching for pages
        if "type=" not in cql.lower():
            cql = f"type=page AND ({cql})"

        params: dict[str, Any] = {
            "cql": cql,
            "limit": limit,
        }

        if include_body:
            params["expand"] = "body.storage"

        # Use v1 search endpoint
        result = await confluence.get_v1("/content/search", params=params)

        pages = []
        for page in result.get("results", []):
            page_data: dict[str, Any] = {
                "id": page.get("id"),
                "title": page.get("title"),
                "space_key": page.get("space", {}).get("key"),
                "status": page.get("status"),
                "type": page.get("type"),
            }

            if include_body and "body" in page:
                storage = page["body"].get("storage", {}).get("value", "")
                page_data["body"] = storage_to_markdown(storage)

            pages.append(page_data)

        return build_response(
            True,
            total=result.get("size", len(pages)),
            pages=pages,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error searching pages")
        return build_response(False, error="Internal error occurred")
