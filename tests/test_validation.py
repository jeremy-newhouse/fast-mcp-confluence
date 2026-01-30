"""Tests for input validation utilities."""

import pytest

from fast_mcp_confluence.utils.validation import (
    AttachmentInput,
    CqlInput,
    LabelInput,
    PageIdInput,
    PageTitleInput,
    SpaceKeyInput,
    ValidationError,
    validate_cql,
    validate_label,
    validate_page_id,
    validate_page_title,
    validate_space_key,
)


class TestSpaceKeyValidation:
    """Tests for space key validation."""

    def test_valid_space_key(self):
        """Valid space keys are accepted."""
        assert validate_space_key("MYSPACE") == "MYSPACE"
        assert validate_space_key("TEST123") == "TEST123"
        assert validate_space_key("MY_SPACE") == "MY_SPACE"

    def test_lowercase_normalized_to_uppercase(self):
        """Lowercase keys are normalized to uppercase."""
        assert validate_space_key("myspace") == "MYSPACE"
        assert validate_space_key("MySpace") == "MYSPACE"

    def test_invalid_space_key_starts_with_number(self):
        """Space keys cannot start with a number."""
        with pytest.raises(ValidationError):
            validate_space_key("123SPACE")

    def test_invalid_space_key_with_dash(self):
        """Space keys cannot contain dashes."""
        with pytest.raises(ValidationError):
            validate_space_key("MY-SPACE")

    def test_invalid_space_key_with_special_chars(self):
        """Space keys cannot contain special characters."""
        with pytest.raises(ValidationError):
            validate_space_key("MY@SPACE")
        with pytest.raises(ValidationError):
            validate_space_key("MY SPACE")


class TestPageIdValidation:
    """Tests for page ID validation."""

    def test_valid_page_id(self):
        """Valid numeric IDs are accepted."""
        assert validate_page_id("12345") == "12345"
        assert validate_page_id("1") == "1"
        assert validate_page_id("999999999") == "999999999"

    def test_invalid_page_id_non_numeric(self):
        """Non-numeric IDs are rejected."""
        with pytest.raises(ValidationError):
            validate_page_id("abc")
        with pytest.raises(ValidationError):
            validate_page_id("12345abc")
        with pytest.raises(ValidationError):
            validate_page_id("12.34")

    def test_invalid_page_id_negative(self):
        """Negative IDs are rejected."""
        with pytest.raises(ValidationError):
            validate_page_id("-123")


class TestPageTitleValidation:
    """Tests for page title validation."""

    def test_valid_page_title(self):
        """Valid titles are accepted."""
        assert validate_page_title("My Page Title") == "My Page Title"
        assert validate_page_title("Page-with-dashes") == "Page-with-dashes"
        assert validate_page_title("Page_with_underscores") == "Page_with_underscores"

    def test_empty_title_rejected(self):
        """Empty titles are rejected."""
        with pytest.raises(ValidationError):
            validate_page_title("")
        with pytest.raises(ValidationError):
            validate_page_title("   ")

    def test_forbidden_characters_rejected(self):
        """Titles with forbidden characters are rejected."""
        forbidden = ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '#']
        for char in forbidden:
            with pytest.raises(ValidationError):
                validate_page_title(f"Page{char}Title")


class TestCqlValidation:
    """Tests for CQL query validation."""

    def test_valid_cql_queries(self):
        """Valid CQL queries are accepted."""
        assert validate_cql("type=page") == "type=page"
        assert validate_cql("space=MYSPACE AND type=page") == "space=MYSPACE AND type=page"
        assert validate_cql('title~"meeting notes"') == 'title~"meeting notes"'
        assert validate_cql("label=important") == "label=important"

    def test_cql_injection_semicolon_blocked(self):
        """Semicolons are blocked to prevent statement chaining."""
        with pytest.raises(ValidationError):
            validate_cql("type=page; DROP TABLE pages;")

    def test_cql_injection_comment_blocked(self):
        """SQL comment patterns are blocked."""
        with pytest.raises(ValidationError):
            validate_cql("type=page -- malicious comment")
        with pytest.raises(ValidationError):
            validate_cql("type=page /* comment */")


class TestLabelValidation:
    """Tests for label validation."""

    def test_valid_labels(self):
        """Valid labels are accepted."""
        assert validate_label("my-label") == "my-label"
        assert validate_label("my_label") == "my_label"
        assert validate_label("label123") == "label123"

    def test_uppercase_normalized_to_lowercase(self):
        """Labels are normalized to lowercase."""
        assert validate_label("MyLabel") == "mylabel"
        assert validate_label("LABEL") == "label"

    def test_invalid_label_with_spaces(self):
        """Labels cannot contain spaces."""
        with pytest.raises(ValidationError):
            validate_label("my label")

    def test_invalid_label_with_special_chars(self):
        """Labels cannot contain special characters."""
        with pytest.raises(ValidationError):
            validate_label("my@label")
        with pytest.raises(ValidationError):
            validate_label("my#label")


class TestAttachmentValidation:
    """Tests for attachment filename validation."""

    def test_valid_filenames(self):
        """Valid filenames are accepted."""
        att = AttachmentInput(filename="report.pdf", content_base64="dGVzdA==")
        assert att.filename == "report.pdf"

        att = AttachmentInput(filename="my-file_v2.txt", content_base64="dGVzdA==")
        assert att.filename == "my-file_v2.txt"

    def test_path_traversal_blocked(self):
        """Path traversal attempts are blocked."""
        with pytest.raises(ValueError):
            AttachmentInput(filename="../../../etc/passwd", content_base64="dGVzdA==")
        with pytest.raises(ValueError):
            AttachmentInput(filename="..\\..\\windows\\system32", content_base64="dGVzdA==")
        with pytest.raises(ValueError):
            AttachmentInput(filename="/etc/passwd", content_base64="dGVzdA==")

    def test_dangerous_extensions_blocked(self):
        """Dangerous file extensions are blocked."""
        dangerous = [".exe", ".bat", ".cmd", ".sh", ".ps1", ".dll", ".so"]
        for ext in dangerous:
            with pytest.raises(ValueError):
                AttachmentInput(filename=f"malware{ext}", content_base64="dGVzdA==")

    def test_hidden_files_blocked(self):
        """Hidden files (starting with dot) are blocked."""
        with pytest.raises(ValueError):
            AttachmentInput(filename=".bashrc", content_base64="dGVzdA==")
        with pytest.raises(ValueError):
            AttachmentInput(filename=".env", content_base64="dGVzdA==")

    def test_null_byte_blocked(self):
        """Null bytes in filename are blocked."""
        with pytest.raises(ValueError):
            AttachmentInput(filename="file\x00.txt", content_base64="dGVzdA==")
