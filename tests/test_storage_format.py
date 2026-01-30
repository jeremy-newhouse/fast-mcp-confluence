"""Tests for markdown to Confluence storage format conversion."""

import pytest

from fast_mcp_confluence.utils.storage_format import (
    markdown_to_storage,
    storage_to_markdown,
    extract_text_from_storage,
)


class TestMarkdownToStorage:
    """Tests for markdown_to_storage conversion."""

    def test_empty_input(self):
        """Empty input returns empty string."""
        assert markdown_to_storage("") == ""
        assert markdown_to_storage(None) == ""

    def test_headings(self):
        """Markdown headings convert to HTML headings."""
        assert "<h1>Hello</h1>" in markdown_to_storage("# Hello")
        assert "<h2>World</h2>" in markdown_to_storage("## World")
        assert "<h3>Test</h3>" in markdown_to_storage("### Test")

    def test_bold(self):
        """Bold markdown converts to strong tags."""
        result = markdown_to_storage("This is **bold** text")
        assert "<strong>bold</strong>" in result

    def test_italic(self):
        """Italic markdown converts to em tags."""
        result = markdown_to_storage("This is *italic* text")
        assert "<em>italic</em>" in result

        result = markdown_to_storage("This is _italic_ text")
        assert "<em>italic</em>" in result

    def test_strikethrough(self):
        """Strikethrough markdown converts to del tags."""
        result = markdown_to_storage("This is ~~deleted~~ text")
        assert "<del>deleted</del>" in result

    def test_inline_code(self):
        """Inline code converts to code tags."""
        result = markdown_to_storage("Use the `print()` function")
        assert "<code>print()</code>" in result

    def test_links(self):
        """Links convert to anchor tags."""
        result = markdown_to_storage("[Click here](https://example.com)")
        assert '<a href="https://example.com">Click here</a>' in result

    def test_bullet_list(self):
        """Bullet lists convert to ul/li tags."""
        result = markdown_to_storage("- Item 1\n- Item 2\n- Item 3")
        assert "<ul>" in result
        assert "<li>Item 1</li>" in result
        assert "<li>Item 2</li>" in result
        assert "<li>Item 3</li>" in result
        assert "</ul>" in result

    def test_numbered_list(self):
        """Numbered lists convert to ol/li tags."""
        result = markdown_to_storage("1. First\n2. Second\n3. Third")
        assert "<ol>" in result
        assert "<li>First</li>" in result
        assert "<li>Second</li>" in result
        assert "</ol>" in result

    def test_code_block(self):
        """Code blocks convert to Confluence code macro."""
        result = markdown_to_storage("```python\nprint('hello')\n```")
        assert 'ac:name="code"' in result
        assert 'language">python</ac:parameter>' in result
        assert "print('hello')" in result

    def test_code_block_no_language(self):
        """Code blocks without language default to plaintext."""
        result = markdown_to_storage("```\nsome code\n```")
        assert 'ac:name="code"' in result
        assert 'language">plaintext</ac:parameter>' in result

    def test_blockquote(self):
        """Blockquotes convert to blockquote tags."""
        result = markdown_to_storage("> This is a quote")
        assert "<blockquote>" in result
        assert "This is a quote" in result
        assert "</blockquote>" in result

    def test_horizontal_rule(self):
        """Horizontal rules convert to hr tags."""
        assert "<hr/>" in markdown_to_storage("---")
        assert "<hr/>" in markdown_to_storage("***")

    def test_paragraph(self):
        """Plain text converts to paragraph tags."""
        result = markdown_to_storage("This is a paragraph.")
        assert "<p>This is a paragraph.</p>" in result


class TestStorageToMarkdown:
    """Tests for storage_to_markdown conversion."""

    def test_empty_input(self):
        """Empty input returns empty string."""
        assert storage_to_markdown("") == ""
        assert storage_to_markdown(None) == ""

    def test_headings(self):
        """HTML headings convert to markdown headings."""
        assert "# Hello" in storage_to_markdown("<h1>Hello</h1>")
        assert "## World" in storage_to_markdown("<h2>World</h2>")

    def test_bold(self):
        """Strong tags convert to bold markdown."""
        result = storage_to_markdown("<p>This is <strong>bold</strong> text</p>")
        assert "**bold**" in result

    def test_italic(self):
        """Em tags convert to italic markdown."""
        result = storage_to_markdown("<p>This is <em>italic</em> text</p>")
        assert "*italic*" in result

    def test_inline_code(self):
        """Code tags convert to backticks."""
        result = storage_to_markdown("<p>Use the <code>print()</code> function</p>")
        assert "`print()`" in result

    def test_links(self):
        """Anchor tags convert to markdown links."""
        result = storage_to_markdown('<a href="https://example.com">Click</a>')
        assert "[Click](https://example.com)" in result

    def test_bullet_list(self):
        """Unordered lists convert to markdown bullets."""
        result = storage_to_markdown("<ul><li>Item 1</li><li>Item 2</li></ul>")
        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_numbered_list(self):
        """Ordered lists convert to markdown numbers."""
        result = storage_to_markdown("<ol><li>First</li><li>Second</li></ol>")
        assert "1. First" in result
        assert "2. Second" in result


class TestExtractTextFromStorage:
    """Tests for extract_text_from_storage."""

    def test_extracts_plain_text(self):
        """Extracts plain text without formatting."""
        result = extract_text_from_storage(
            "<p>Hello <strong>world</strong></p><p>How are you?</p>"
        )
        assert "Hello" in result
        assert "world" in result
        assert "How are you" in result
        assert "<" not in result
        assert ">" not in result

    def test_empty_input(self):
        """Empty input returns empty string."""
        assert extract_text_from_storage("") == ""
        assert extract_text_from_storage(None) == ""


class TestRoundTrip:
    """Test roundtrip conversion (markdown -> storage -> markdown)."""

    def test_simple_roundtrip(self):
        """Simple content survives roundtrip conversion."""
        original = "# Hello\n\nThis is **bold** and *italic*."
        storage = markdown_to_storage(original)
        back = storage_to_markdown(storage)

        assert "# Hello" in back or "Hello" in back
        assert "**bold**" in back or "bold" in back

    def test_list_roundtrip(self):
        """Lists survive roundtrip conversion."""
        original = "- Item 1\n- Item 2\n- Item 3"
        storage = markdown_to_storage(original)
        back = storage_to_markdown(storage)

        assert "Item 1" in back
        assert "Item 2" in back
        assert "Item 3" in back
