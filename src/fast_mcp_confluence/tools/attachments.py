"""MCP tools for Confluence attachment operations.

Tools:
- get_attachments: List attachments on a page
- get_attachment: Get attachment metadata
- add_attachment: Upload a new attachment
- delete_attachment: Delete an attachment
- download_attachment: Get attachment download URL
"""

import base64
from typing import Annotated, Any

from pydantic import Field

from ..logging_config import get_logger
from ..server import confluence, mcp
from ..services.confluence_client import ConfluenceError
from ..utils.validation import (
    AttachmentInput,
    ValidationError,
    build_response,
    validate_page_id,
)

logger = get_logger(__name__)


@mcp.tool(description="List attachments on a Confluence page.")
async def get_attachments(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    limit: Annotated[
        int,
        Field(description="Maximum number of attachments to return", ge=1, le=250),
    ] = 25,
) -> dict[str, Any]:
    """Get all attachments on a page."""
    try:
        page_id = validate_page_id(page_id)

        result = await confluence.get_v2(
            f"/pages/{page_id}/attachments",
            params={"limit": limit}
        )

        attachments = []
        for att in result.get("results", []):
            attachments.append({
                "id": att.get("id"),
                "title": att.get("title"),
                "media_type": att.get("mediaType"),
                "file_size": att.get("fileSize"),
                "comment": att.get("comment"),
                "version": att.get("version", {}).get("number"),
                "created_at": att.get("createdAt"),
            })

        return build_response(
            True,
            page_id=page_id,
            total=len(attachments),
            attachments=attachments,
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting attachments")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get metadata for a specific Confluence attachment.")
async def get_attachment(
    attachment_id: Annotated[str, Field(description="Attachment ID (numeric)")],
) -> dict[str, Any]:
    """Get detailed information about an attachment."""
    try:
        attachment_id = validate_page_id(attachment_id)

        result = await confluence.get_v2(f"/attachments/{attachment_id}")

        return build_response(
            True,
            id=result.get("id"),
            title=result.get("title"),
            media_type=result.get("mediaType"),
            file_size=result.get("fileSize"),
            comment=result.get("comment"),
            page_id=result.get("pageId"),
            version=result.get("version", {}).get("number"),
            created_at=result.get("createdAt"),
            download_link=result.get("downloadLink"),
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting attachment")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Upload an attachment to a Confluence page.")
async def add_attachment(
    page_id: Annotated[str, Field(description="Page ID (numeric)")],
    filename: Annotated[
        str,
        Field(description="Filename for the attachment (e.g., 'report.pdf')"),
    ],
    content_base64: Annotated[
        str,
        Field(description="Base64-encoded file content"),
    ],
    content_type: Annotated[
        str,
        Field(description="MIME type (e.g., 'application/pdf', 'image/png')"),
    ] = "application/octet-stream",
    comment: Annotated[
        str | None,
        Field(description="Optional comment for the attachment"),
    ] = None,
) -> dict[str, Any]:
    """Upload a new attachment to a page.

    The file content must be base64-encoded.
    """
    try:
        page_id = validate_page_id(page_id)

        # Validate attachment input
        att_input = AttachmentInput(
            filename=filename,
            content_base64=content_base64,
            content_type=content_type,
        )

        # Decode base64 content
        try:
            file_content = base64.b64decode(att_input.content_base64)
        except Exception:
            return build_response(False, error="Invalid base64 content", field="content_base64")

        # Upload via multipart - use v1 API endpoint
        result = await confluence.post_multipart(
            f"/rest/api/content/{page_id}/child/attachment",
            filename=att_input.filename,
            content=file_content,
            content_type=att_input.content_type,
        )

        # Result might be a list for attachment uploads
        if isinstance(result, list) and result:
            att = result[0]
        else:
            att = result

        return build_response(
            True,
            id=att.get("id"),
            title=att.get("title"),
            page_id=page_id,
            file_size=len(file_content),
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ValueError as e:
        return build_response(False, error=str(e))
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error adding attachment")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Delete a Confluence attachment.")
async def delete_attachment(
    attachment_id: Annotated[str, Field(description="Attachment ID (numeric)")],
) -> dict[str, Any]:
    """Delete an attachment."""
    try:
        attachment_id = validate_page_id(attachment_id)

        # Use v1 API for attachment deletion
        await confluence.delete_v1(f"/content/{attachment_id}")

        return build_response(True, message=f"Attachment {attachment_id} deleted successfully")

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error deleting attachment")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Get the download URL for a Confluence attachment.")
async def download_attachment(
    attachment_id: Annotated[str, Field(description="Attachment ID (numeric)")],
) -> dict[str, Any]:
    """Get the download URL for an attachment.

    Returns the download link that can be used to fetch the file content.
    """
    try:
        attachment_id = validate_page_id(attachment_id)

        result = await confluence.get_v2(f"/attachments/{attachment_id}")

        download_link = result.get("downloadLink")
        if not download_link:
            return build_response(False, error="Download link not available")

        return build_response(
            True,
            id=result.get("id"),
            title=result.get("title"),
            download_link=download_link,
            media_type=result.get("mediaType"),
            file_size=result.get("fileSize"),
        )

    except ValidationError as e:
        return build_response(False, error=str(e), field=e.field)
    except ConfluenceError as e:
        return build_response(False, error=str(e), status_code=e.status_code)
    except Exception:
        logger.exception("Unexpected error getting download link")
        return build_response(False, error="Internal error occurred")
