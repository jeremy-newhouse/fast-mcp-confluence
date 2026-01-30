"""Input validation utilities for Confluence API parameters.

This module provides two validation approaches:
1. Pydantic models (SpaceKeyInput, PageIdInput, etc.) for type-safe validation
2. Standalone functions (validate_space_key, etc.) for convenience

Security Features:
- Path traversal prevention in filenames
- Dangerous file extension blocking
- CQL injection pattern detection
- Input length limits to prevent DoS
- Page title character validation
"""

import re
from typing import Any

import bleach
from pydantic import BaseModel, ConfigDict, Field, field_validator

# =============================================================================
# XSS Sanitization Configuration (using bleach allowlist approach)
# =============================================================================

# Safe HTML tags that are allowed in responses
ALLOWED_HTML_TAGS = [
    "p",
    "br",
    "b",
    "i",
    "u",
    "strong",
    "em",
    "a",
    "ul",
    "ol",
    "li",
    "code",
    "pre",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "span",
    "div",
    "table",
    "tr",
    "td",
    "th",
    "thead",
    "tbody",
]

# Safe attributes for allowed tags
ALLOWED_HTML_ATTRIBUTES = {
    "a": ["href", "title"],
    "span": ["class"],
    "div": ["class"],
    "code": ["class"],
    "pre": ["class"],
    "table": ["class"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan"],
}

# Safe URL protocols
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


# =============================================================================
# Pydantic Validation Models
# =============================================================================


class SpaceKeyInput(BaseModel):
    """Validated Confluence space key input.

    Validates that space keys are uppercase letters/numbers/underscores
    starting with a letter, max 255 characters.

    Example:
        >>> validated = SpaceKeyInput(space_key="myspace")
        >>> validated.space_key
        'MYSPACE'
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    space_key: str = Field(..., max_length=255, description="Space key (e.g., MYSPACE)")

    @field_validator("space_key")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate and normalize space key format."""
        v = v.strip().upper()
        if not re.match(r"^[A-Z][A-Z0-9_]*$", v):
            raise ValueError(
                f"Invalid space key '{v}'. Must start with letter, "
                "contain only letters/numbers/underscores"
            )
        return v


class PageIdInput(BaseModel):
    """Validated Confluence page ID input.

    Page IDs in Confluence are numeric strings.

    Example:
        >>> validated = PageIdInput(page_id="12345")
        >>> validated.page_id
        '12345'
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    page_id: str = Field(..., description="Page ID (numeric)")

    @field_validator("page_id")
    @classmethod
    def validate_numeric(cls, v: str) -> str:
        """Ensure ID is purely numeric."""
        v = v.strip()
        if not v.isdigit():
            raise ValueError("Page ID must be numeric")
        return v


class PageTitleInput(BaseModel):
    """Validated Confluence page title input.

    Page titles cannot contain certain characters: / \\ : * ? " < > | #

    Example:
        >>> validated = PageTitleInput(title="My Page Title")
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(..., max_length=255, description="Page title")

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        """Validate page title."""
        v = v.strip()
        if not v:
            raise ValueError("Page title cannot be empty")
        # Confluence forbids certain characters in page titles
        forbidden = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '#']
        for char in forbidden:
            if char in v:
                raise ValueError(f"Page title cannot contain '{char}'")
        return v


class CqlInput(BaseModel):
    """Validated CQL query input with injection prevention.

    Security features:
    - Maximum length of 10,000 characters
    - Blocks SQL-like injection patterns (;, --, /*, */)

    Example:
        >>> query = CqlInput(cql="type=page AND space=MYSPACE")
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    cql: str = Field(..., max_length=10000, description="CQL query string")

    @field_validator("cql")
    @classmethod
    def validate_cql(cls, v: str) -> str:
        """Check for potential injection patterns."""
        v = v.strip()
        # Check for injection patterns
        # Note: CQL has limited injection surface, but we block:
        # - SQL-style comments and statement terminators
        # - Backslash sequences that could escape quotes
        dangerous_patterns = [
            r";",           # Statement terminator
            r"--",          # SQL comment
            r"/\*",         # Block comment start
            r"\*/",         # Block comment end
            r"\\[\"']",     # Escaped quotes (bypass attempts)
        ]
        v_lower = v.lower()
        for pattern in dangerous_patterns:
            if re.search(pattern, v_lower):
                raise ValueError("CQL contains potentially dangerous characters")

        # Check for unbalanced quotes which could indicate injection attempt
        quote_count = v.count('"')
        if quote_count % 2 != 0:
            raise ValueError("CQL contains unbalanced quotes")

        return v


class LabelInput(BaseModel):
    """Validated label input.

    Labels in Confluence are lowercase, alphanumeric with hyphens/underscores.

    Example:
        >>> validated = LabelInput(name="my-label")
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(..., max_length=255, description="Label name")

    @field_validator("name")
    @classmethod
    def validate_label(cls, v: str) -> str:
        """Validate label format."""
        v = v.strip().lower()
        if not re.match(r"^[a-z0-9_-]+$", v):
            raise ValueError(
                "Label must contain only lowercase letters, numbers, "
                "underscores, and hyphens"
            )
        return v


class LabelListInput(BaseModel):
    """Validated list of labels.

    Example:
        >>> labels = LabelListInput(labels=["backend", "high-priority"])
    """

    labels: list[str] = Field(default_factory=list, description="List of labels")

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, v: list[str]) -> list[str]:
        """Validate each label format."""
        validated = []
        for label in v:
            label = label.strip().lower()
            if not label:
                continue
            if len(label) > 255:
                raise ValueError("Label exceeds 255 character limit")
            if not re.match(r"^[a-z0-9_-]+$", label):
                raise ValueError(
                    f"Label '{label}' contains invalid characters. "
                    "Use only lowercase letters, numbers, underscores, hyphens"
                )
            validated.append(label)
        return validated


class AttachmentInput(BaseModel):
    """Validated attachment input with security checks.

    Security features:
    - Filename path traversal prevention (blocks .., /, \\)
    - Dangerous extension blocking (.exe, .bat, .cmd, .sh, .ps1, .dll, .so)
    - Size limit of ~100MB for base64 content

    Example:
        >>> att = AttachmentInput(
        ...     filename="report.pdf",
        ...     content_base64="SGVsbG8gV29ybGQ="
        ... )
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    filename: str = Field(..., max_length=255, description="Attachment filename")
    content_base64: str = Field(
        ...,
        max_length=140_000_000,  # ~100MB after base64 encoding
        description="Base64-encoded file content",
    )
    content_type: str = Field(
        default="application/octet-stream",
        description="MIME type (e.g., 'text/plain', 'image/png')",
    )

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        """Prevent path traversal and dangerous extensions."""
        v = v.strip()
        # Block path traversal attempts
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Filename contains invalid path characters")
        # Block null bytes
        if "\x00" in v:
            raise ValueError("Filename contains invalid characters")
        # Block hidden/dotfiles (e.g., .bashrc, .env, .gitignore)
        if v.startswith("."):
            raise ValueError("Hidden files (starting with dot) are not allowed")
        # Block dangerous extensions
        dangerous_extensions = {".exe", ".bat", ".cmd", ".sh", ".ps1", ".dll", ".so"}
        ext = ("." + v.rsplit(".", 1)[-1].lower()) if "." in v else ""
        if ext in dangerous_extensions:
            raise ValueError(f"File type {ext} is not allowed for security reasons")
        # Validate characters (alphanumeric, dots, hyphens, underscores, spaces)
        if not re.match(r"^[\w\-. ]+$", v):
            raise ValueError("Filename contains invalid characters")
        return v


class CommentInput(BaseModel):
    """Validated comment body input.

    Supports markdown formatting. Maximum 32,767 characters.

    Example:
        >>> comment = CommentInput(body="This is a **bold** comment")
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    body: str = Field(
        ...,
        max_length=32767,
        description="Comment text with markdown support",
    )

    @field_validator("body")
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Ensure comment is not empty."""
        if not v.strip():
            raise ValueError("Comment body cannot be empty")
        return v


class NumericIdInput(BaseModel):
    """Validated numeric ID input.

    Used for attachment IDs, comment IDs, etc.

    Example:
        >>> id_input = NumericIdInput(id="12345")
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    id: str = Field(..., description="Numeric ID")

    @field_validator("id")
    @classmethod
    def validate_numeric(cls, v: str) -> str:
        """Ensure ID is purely numeric."""
        v = v.strip()
        if not v.isdigit():
            raise ValueError("ID must be numeric")
        return v


class AccountIdInput(BaseModel):
    """Validated Atlassian account ID input.

    Account IDs are typically in format: 712020:uuid or 5xxxxxxxxxxxxx

    Example:
        >>> account = AccountIdInput(account_id="712020:abc-def-123")
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    account_id: str = Field(..., min_length=10, max_length=128, description="Atlassian account ID")

    @field_validator("account_id")
    @classmethod
    def validate_format(cls, v: str) -> str:
        """Validate account ID format."""
        v = v.strip()
        # Allow alphanumeric, colons, hyphens, underscores
        if not re.match(r"^[a-zA-Z0-9:_-]+$", v):
            raise ValueError("Account ID contains invalid characters")
        return v


class PropertyKeyInput(BaseModel):
    """Validated content property key.

    Property keys are alphanumeric with underscores/hyphens.

    Example:
        >>> prop = PropertyKeyInput(key="my-property")
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    key: str = Field(..., max_length=255, description="Property key")

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        """Validate property key format."""
        v = v.strip()
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", v):
            raise ValueError(
                "Property key must start with a letter and contain only "
                "letters, numbers, underscores, and hyphens"
            )
        return v


# Allowed fields for bulk updates (security: prevent updating sensitive fields)
ALLOWED_BULK_UPDATE_FIELDS = {
    "title",
    "status",
    "parentId",
}


class BulkUpdateFieldsInput(BaseModel):
    """Validated bulk update fields.

    Only allows updates to safe, known fields.

    Example:
        >>> updates = BulkUpdateFieldsInput(
        ...     updates={"title": "New Title"}
        ... )
    """

    updates: dict[str, Any] = Field(..., description="Field updates")

    @field_validator("updates")
    @classmethod
    def validate_fields(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate that only allowed fields are being updated."""
        if not v:
            raise ValueError("No updates provided")

        for field_name in v.keys():
            if field_name not in ALLOWED_BULK_UPDATE_FIELDS:
                raise ValueError(
                    f"Field '{field_name}' is not allowed in bulk updates. "
                    f"Allowed fields: {', '.join(sorted(ALLOWED_BULK_UPDATE_FIELDS))}"
                )
        return v


# =============================================================================
# Validation Error
# =============================================================================


class ValidationError(Exception):
    """Raised when input validation fails."""

    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")


# =============================================================================
# Standalone Validation Functions
# =============================================================================


def validate_space_key(space_key: str) -> str:
    """Validate Confluence space key format.

    Args:
        space_key: Space key to validate (e.g., MYSPACE)

    Returns:
        The validated space key (uppercase)

    Raises:
        ValidationError: If the space key format is invalid
    """
    try:
        validated = SpaceKeyInput(space_key=space_key)
        return validated.space_key
    except ValueError as e:
        raise ValidationError("space_key", str(e))


def validate_page_id(page_id: str) -> str:
    """Validate Confluence page ID format.

    Args:
        page_id: Page ID to validate (numeric string)

    Returns:
        The validated page ID

    Raises:
        ValidationError: If the page ID format is invalid
    """
    try:
        validated = PageIdInput(page_id=page_id)
        return validated.page_id
    except ValueError as e:
        raise ValidationError("page_id", str(e))


def validate_space_id(space_id: str) -> str:
    """Validate Confluence space ID format.

    Space IDs in Confluence are numeric strings (same format as page IDs).

    Args:
        space_id: Space ID to validate (numeric string)

    Returns:
        The validated space ID

    Raises:
        ValidationError: If the space ID format is invalid
    """
    space_id = space_id.strip()
    if not space_id.isdigit():
        raise ValidationError("space_id", "Space ID must be numeric")
    return space_id


def validate_page_title(title: str) -> str:
    """Validate Confluence page title.

    Args:
        title: Page title to validate

    Returns:
        The validated title

    Raises:
        ValidationError: If the title is invalid
    """
    try:
        validated = PageTitleInput(title=title)
        return validated.title
    except ValueError as e:
        raise ValidationError("title", str(e))


def validate_cql(cql: str) -> str:
    """Validate CQL query.

    Args:
        cql: CQL query to validate

    Returns:
        The validated CQL query

    Raises:
        ValidationError: If the CQL contains dangerous patterns
    """
    try:
        validated = CqlInput(cql=cql)
        return validated.cql
    except ValueError as e:
        raise ValidationError("cql", str(e))


def validate_label(label: str) -> str:
    """Validate label format.

    Args:
        label: Label to validate

    Returns:
        The validated label (lowercase)

    Raises:
        ValidationError: If the label format is invalid
    """
    try:
        validated = LabelInput(name=label)
        return validated.name
    except ValueError as e:
        raise ValidationError("label", str(e))


def validate_labels(labels: list[str] | None) -> list[str] | None:
    """Validate list of labels.

    Args:
        labels: List of labels to validate

    Returns:
        The validated labels list or None

    Raises:
        ValidationError: If any label is invalid
    """
    if not labels:
        return labels

    try:
        validated = LabelListInput(labels=labels)
        return validated.labels if validated.labels else None
    except ValueError as e:
        raise ValidationError("labels", str(e))


def validate_account_id(account_id: str | None, field_name: str = "account_id") -> str | None:
    """Validate Atlassian account ID.

    Args:
        account_id: Account ID to validate
        field_name: Name of the field for error messages

    Returns:
        The validated account ID or None

    Raises:
        ValidationError: If the account ID format is invalid
    """
    if account_id is None or account_id == "":
        return account_id

    try:
        validated = AccountIdInput(account_id=account_id)
        return validated.account_id
    except ValueError as e:
        raise ValidationError(field_name, str(e))


def validate_comment_body(body: str) -> str:
    """Validate comment body.

    Args:
        body: Comment body text to validate

    Returns:
        The validated body

    Raises:
        ValidationError: If the body is invalid
    """
    try:
        validated = CommentInput(body=body)
        return validated.body
    except ValueError as e:
        raise ValidationError("body", str(e))


def validate_property_key(key: str) -> str:
    """Validate content property key.

    Args:
        key: Property key to validate

    Returns:
        The validated key

    Raises:
        ValidationError: If the key format is invalid
    """
    try:
        validated = PropertyKeyInput(key=key)
        return validated.key
    except ValueError as e:
        raise ValidationError("key", str(e))


# =============================================================================
# XSS Sanitization Functions
# =============================================================================


def sanitize_for_response(data: Any) -> Any:
    """Sanitize data for safe inclusion in responses.

    Uses bleach library with allowlist approach for robust XSS prevention:
    - Only allows safe HTML tags (p, br, a, ul, ol, li, code, pre, etc.)
    - Only allows safe attributes (href, title on links)
    - Only allows safe URL protocols (http, https, mailto)
    - Strips all other HTML content

    Args:
        data: Data to sanitize (string, dict, list, or other)

    Returns:
        Sanitized data with dangerous HTML removed
    """
    if isinstance(data, str):
        return bleach.clean(
            data,
            tags=ALLOWED_HTML_TAGS,
            attributes=ALLOWED_HTML_ATTRIBUTES,
            protocols=ALLOWED_PROTOCOLS,
            strip=True,
        )

    if isinstance(data, dict):
        return {k: sanitize_for_response(v) for k, v in data.items()}

    if isinstance(data, list):
        return [sanitize_for_response(item) for item in data]

    return data


def build_response(success: bool, **data: Any) -> dict[str, Any]:
    """Build a sanitized tool response.

    This is the standard way to build responses from MCP tools.
    All data values are automatically sanitized to remove potentially
    dangerous HTML content (XSS prevention).

    Args:
        success: Whether the operation succeeded.
        **data: Response data fields to include.

    Returns:
        Dict with 'success' field and sanitized data.

    Example:
        >>> build_response(True, page_id="12345", data={"title": "Test"})
        {"success": True, "page_id": "12345", "data": {"title": "Test"}}
    """
    sanitized = {k: sanitize_for_response(v) for k, v in data.items()}
    return {"success": success, **sanitized}
