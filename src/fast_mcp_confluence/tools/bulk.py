"""MCP tools for Confluence bulk operations.

Tools:
- bulk_update_pages: Update multiple pages in parallel
- bulk_add_labels: Add labels to multiple pages
- bulk_delete_pages: Delete multiple pages
- bulk_archive_pages: Archive multiple pages

Uses asyncio.gather() for parallel execution with configurable concurrency.
"""

import asyncio
from typing import Annotated, Any

from pydantic import Field

from ..config import get_settings
from ..logging_config import get_logger
from ..server import confluence, mcp
from ..services.confluence_client import ConfluenceError
from ..utils.storage_format import markdown_to_storage
from ..utils.validation import (
    LabelInput,
    ValidationError,
    build_response,
    validate_page_id,
    validate_page_title,
)

logger = get_logger(__name__)


async def _update_single_page(
    page_id: str,
    title: str | None,
    body: str | None,
) -> dict[str, Any]:
    """Update a single page, returning result dict."""
    try:
        page_id = validate_page_id(page_id)

        # Get current page for version
        current = await confluence.get_v2(f"/pages/{page_id}")
        current_version = current.get("version", {}).get("number", 1)

        request_body: dict[str, Any] = {
            "id": page_id,
            "status": "current",
            "version": {"number": current_version + 1},
        }

        if title:
            request_body["title"] = validate_page_title(title)

        if body:
            request_body["body"] = {
                "representation": "storage",
                "value": markdown_to_storage(body),
            }

        result = await confluence.put_v2(f"/pages/{page_id}", body=request_body)

        return {
            "page_id": page_id,
            "success": True,
            "title": result.get("title"),
            "version": result.get("version", {}).get("number"),
        }
    except (ValidationError, ConfluenceError) as e:
        return {
            "page_id": page_id,
            "success": False,
            "error": str(e),
        }
    except Exception as e:
        logger.exception("Error updating page %s", page_id)
        return {
            "page_id": page_id,
            "success": False,
            "error": "Internal error",
        }


async def _add_labels_to_page(
    page_id: str,
    labels: list[str],
) -> dict[str, Any]:
    """Add labels to a single page, returning result dict."""
    try:
        page_id = validate_page_id(page_id)

        # Validate labels
        validated_labels = []
        for label in labels:
            label_input = LabelInput(name=label)
            validated_labels.append(label_input.name)

        # Use v1 API - same as add_page_labels
        request_body = [{"prefix": "global", "name": name} for name in validated_labels]
        await confluence.post_v1(f"/content/{page_id}/label", body=request_body)

        return {
            "page_id": page_id,
            "success": True,
            "labels_added": validated_labels,
        }
    except (ValidationError, ConfluenceError, ValueError) as e:
        return {
            "page_id": page_id,
            "success": False,
            "error": str(e),
        }
    except Exception as e:
        logger.exception("Error adding labels to page %s", page_id)
        return {
            "page_id": page_id,
            "success": False,
            "error": "Internal error",
        }


async def _delete_single_page(page_id: str) -> dict[str, Any]:
    """Delete a single page, returning result dict."""
    try:
        page_id = validate_page_id(page_id)
        # Use v1 API for page deletion (v2 returns 404)
        await confluence.delete_v1(f"/content/{page_id}")

        return {
            "page_id": page_id,
            "success": True,
        }
    except (ValidationError, ConfluenceError) as e:
        return {
            "page_id": page_id,
            "success": False,
            "error": str(e),
        }
    except Exception as e:
        logger.exception("Error deleting page %s", page_id)
        return {
            "page_id": page_id,
            "success": False,
            "error": "Internal error",
        }


async def _archive_single_page(page_id: str) -> dict[str, Any]:
    """Archive a single page, returning result dict."""
    try:
        page_id = validate_page_id(page_id)

        # Get current page info
        current = await confluence.get_v2(f"/pages/{page_id}")
        current_version = current.get("version", {}).get("number", 1)
        current_title = current.get("title")
        current_status = current.get("status")

        if current_status == "archived":
            return {
                "page_id": page_id,
                "success": True,
                "title": current_title,
                "already_archived": True,
            }

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

        return {
            "page_id": page_id,
            "success": True,
            "title": result.get("title"),
            "status": result.get("status"),
        }
    except (ValidationError, ConfluenceError) as e:
        return {
            "page_id": page_id,
            "success": False,
            "error": str(e),
        }
    except Exception as e:
        logger.exception("Error archiving page %s", page_id)
        return {
            "page_id": page_id,
            "success": False,
            "error": "Internal error",
        }


@mcp.tool(description="Update multiple Confluence pages in parallel.")
async def bulk_update_pages(
    updates: Annotated[
        list[dict[str, Any]],
        Field(
            description=(
                "List of updates. Each update is a dict with: "
                "page_id (required), title (optional), body (optional in markdown)"
            )
        ),
    ],
) -> dict[str, Any]:
    """Update multiple pages in parallel.

    Each update object should contain:
    - page_id: The page ID to update (required)
    - title: New title for the page (optional)
    - body: New body content in markdown (optional)

    At least one of title or body must be provided.
    """
    try:
        settings = get_settings()
        max_batch = settings.bulk_max_batch_size
        max_concurrent = settings.bulk_concurrent_requests

        if not updates:
            return build_response(False, error="No updates provided")

        if len(updates) > max_batch:
            return build_response(
                False,
                error=f"Too many updates. Maximum batch size is {max_batch}",
            )

        # Validate each update has required fields
        for i, update in enumerate(updates):
            if "page_id" not in update:
                return build_response(
                    False,
                    error=f"Update at index {i} missing 'page_id'",
                )
            if "title" not in update and "body" not in update:
                return build_response(
                    False,
                    error=f"Update at index {i} must have 'title' or 'body'",
                )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def limited_update(update: dict) -> dict[str, Any]:
            async with semaphore:
                return await _update_single_page(
                    page_id=update["page_id"],
                    title=update.get("title"),
                    body=update.get("body"),
                )

        # Execute updates in parallel
        tasks = [limited_update(update) for update in updates]
        results = await asyncio.gather(*tasks)

        succeeded = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        return build_response(
            True,
            total=len(results),
            succeeded=len(succeeded),
            failed=len(failed),
            results=results,
        )

    except Exception:
        logger.exception("Unexpected error in bulk update")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Add labels to multiple Confluence pages in parallel.")
async def bulk_add_labels(
    page_ids: Annotated[
        list[str],
        Field(description="List of page IDs (numeric)"),
    ],
    labels: Annotated[
        list[str],
        Field(description="Labels to add to all pages"),
    ],
) -> dict[str, Any]:
    """Add the same labels to multiple pages in parallel."""
    try:
        settings = get_settings()
        max_batch = settings.bulk_max_batch_size
        max_concurrent = settings.bulk_concurrent_requests

        if not page_ids:
            return build_response(False, error="No page IDs provided")

        if not labels:
            return build_response(False, error="No labels provided")

        if len(page_ids) > max_batch:
            return build_response(
                False,
                error=f"Too many pages. Maximum batch size is {max_batch}",
            )

        # Validate labels upfront
        validated_labels = []
        for label in labels:
            label_input = LabelInput(name=label)
            validated_labels.append(label_input.name)

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def limited_add_labels(page_id: str) -> dict[str, Any]:
            async with semaphore:
                return await _add_labels_to_page(page_id, validated_labels)

        # Execute in parallel
        tasks = [limited_add_labels(page_id) for page_id in page_ids]
        results = await asyncio.gather(*tasks)

        succeeded = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        return build_response(
            True,
            total=len(results),
            succeeded=len(succeeded),
            failed=len(failed),
            labels=validated_labels,
            results=results,
        )

    except ValueError as e:
        return build_response(False, error=str(e))
    except Exception:
        logger.exception("Unexpected error in bulk add labels")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Delete multiple Confluence pages in parallel.")
async def bulk_delete_pages(
    page_ids: Annotated[
        list[str],
        Field(description="List of page IDs to delete (numeric)"),
    ],
) -> dict[str, Any]:
    """Delete multiple pages in parallel.

    Warning: This operation is destructive. Pages will be moved to trash
    or permanently deleted depending on Confluence settings.
    """
    try:
        settings = get_settings()
        max_batch = settings.bulk_max_batch_size
        max_concurrent = settings.bulk_concurrent_requests

        if not page_ids:
            return build_response(False, error="No page IDs provided")

        if len(page_ids) > max_batch:
            return build_response(
                False,
                error=f"Too many pages. Maximum batch size is {max_batch}",
            )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def limited_delete(page_id: str) -> dict[str, Any]:
            async with semaphore:
                return await _delete_single_page(page_id)

        # Execute in parallel
        tasks = [limited_delete(page_id) for page_id in page_ids]
        results = await asyncio.gather(*tasks)

        succeeded = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        return build_response(
            True,
            total=len(results),
            succeeded=len(succeeded),
            failed=len(failed),
            results=results,
        )

    except Exception:
        logger.exception("Unexpected error in bulk delete")
        return build_response(False, error="Internal error occurred")


@mcp.tool(description="Archive multiple Confluence pages in parallel.")
async def bulk_archive_pages(
    page_ids: Annotated[
        list[str],
        Field(description="List of page IDs to archive (numeric)"),
    ],
) -> dict[str, Any]:
    """Archive multiple pages in parallel.

    Archived pages are hidden from normal views but can be restored later.
    This is a non-destructive alternative to bulk deletion.
    """
    try:
        settings = get_settings()
        max_batch = settings.bulk_max_batch_size
        max_concurrent = settings.bulk_concurrent_requests

        if not page_ids:
            return build_response(False, error="No page IDs provided")

        if len(page_ids) > max_batch:
            return build_response(
                False,
                error=f"Too many pages. Maximum batch size is {max_batch}",
            )

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def limited_archive(page_id: str) -> dict[str, Any]:
            async with semaphore:
                return await _archive_single_page(page_id)

        # Execute in parallel
        tasks = [limited_archive(page_id) for page_id in page_ids]
        results = await asyncio.gather(*tasks)

        succeeded = [r for r in results if r.get("success")]
        failed = [r for r in results if not r.get("success")]

        return build_response(
            True,
            total=len(results),
            succeeded=len(succeeded),
            failed=len(failed),
            results=results,
        )

    except Exception:
        logger.exception("Unexpected error in bulk archive")
        return build_response(False, error="Internal error occurred")
