"""Markdown to Confluence storage format conversion utilities.

This module provides bidirectional conversion between markdown and
Confluence's XHTML-based storage format.

Functions:
- markdown_to_storage(): Convert markdown text to Confluence storage format
- storage_to_markdown(): Convert storage format back to readable markdown

Supported markdown features (bidirectional):
- Headings (# through ######)
- Bold (**text**)
- Italic (*text* or _text_)
- Strikethrough (~~text~~)
- Links ([text](url))
- Images (![alt](url))
- Bullet lists (- item or * item)
- Numbered lists (1. item)
- Code blocks (```language code```)
- Inline code (`code`)
- Blockquotes (> text)
- Horizontal rules (---)
- Tables (| col | col |)
"""

import html
import re
from typing import Any


# Supported code languages for Confluence code macro
SUPPORTED_LANGUAGES = {
    "actionscript3",
    "applescript",
    "bash",
    "c",
    "csharp",
    "coldfusion",
    "cpp",
    "css",
    "delphi",
    "diff",
    "erlang",
    "groovy",
    "html",
    "java",
    "javafx",
    "javascript",
    "json",
    "perl",
    "php",
    "plaintext",
    "powershell",
    "python",
    "ruby",
    "sass",
    "scala",
    "shell",
    "sql",
    "vb",
    "xml",
    "yaml",
}


def _escape_xml(text: str) -> str:
    """Escape text for safe inclusion in XML/HTML."""
    return html.escape(text, quote=True)


def _create_code_macro(code: str, language: str | None = None) -> str:
    """Create Confluence code macro XML.

    Args:
        code: The code content.
        language: Programming language for syntax highlighting.

    Returns:
        Confluence structured macro XML for code block.
    """
    # Normalize language
    if language:
        language = language.lower()
        # Map common aliases
        language_map = {
            "js": "javascript",
            "ts": "javascript",
            "typescript": "javascript",
            "py": "python",
            "rb": "ruby",
            "sh": "bash",
            "zsh": "bash",
            "yml": "yaml",
            "cs": "csharp",
            "c++": "cpp",
        }
        language = language_map.get(language, language)
        if language not in SUPPORTED_LANGUAGES:
            language = "plaintext"
    else:
        language = "plaintext"

    # Escape CDATA end sequence in code
    code = code.replace("]]>", "]]]]><![CDATA[>")

    return f'''<ac:structured-macro ac:name="code">
<ac:parameter ac:name="language">{language}</ac:parameter>
<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>
</ac:structured-macro>'''


def _convert_inline_formatting(text: str) -> str:
    """Convert inline markdown formatting to HTML.

    Args:
        text: Text with markdown inline formatting.

    Returns:
        Text with HTML inline formatting.
    """
    # Bold: **text** -> <strong>text</strong>
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)

    # Italic: *text* -> <em>text</em> (but not inside **)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)

    # Italic: _text_ -> <em>text</em>
    text = re.sub(r"(?<![a-zA-Z0-9])_([^_]+)_(?![a-zA-Z0-9])", r"<em>\1</em>", text)

    # Strikethrough: ~~text~~ -> <del>text</del>
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)

    # Inline code: `code` -> <code>code</code>
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    # Links: [text](url) -> <a href="url">text</a>
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # Images: ![alt](url) -> <ac:image><ri:url ri:value="url"/></ac:image>
    text = re.sub(
        r"!\[([^\]]*)\]\(([^)]+)\)",
        r'<ac:image><ri:url ri:value="\2"/></ac:image>',
        text,
    )

    return text


def markdown_to_storage(text: str) -> str:
    """Convert markdown to Confluence storage format.

    This is the primary conversion used when creating/updating pages.
    The LLM provides markdown, we convert to storage format for the API.

    Args:
        text: Markdown text to convert.

    Returns:
        Confluence storage format XHTML.

    Example:
        >>> markdown_to_storage("# Hello\\n\\nThis is **bold**.")
        '<h1>Hello</h1><p>This is <strong>bold</strong>.</p>'
    """
    if not text:
        return ""

    # Normalize escaped newlines
    text = text.replace("\\n", "\n")

    result_parts: list[str] = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # Code block: ```language ... ```
        if line.strip().startswith("```"):
            language = line.strip()[3:].strip() or None
            code_lines: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            code_content = "\n".join(code_lines)
            result_parts.append(_create_code_macro(code_content, language))
            i += 1
            continue

        # Heading: # ## ### etc.
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            level = len(heading_match.group(1))
            text_content = _convert_inline_formatting(_escape_xml(heading_match.group(2)))
            result_parts.append(f"<h{level}>{text_content}</h{level}>")
            i += 1
            continue

        # Horizontal rule: --- or ***
        if re.match(r"^[-*]{3,}\s*$", line.strip()):
            result_parts.append("<hr/>")
            i += 1
            continue

        # Blockquote: > text
        if line.startswith(">"):
            quote_lines: list[str] = []
            while i < len(lines) and lines[i].startswith(">"):
                quote_text = lines[i][1:].strip()
                quote_lines.append(_convert_inline_formatting(_escape_xml(quote_text)))
                i += 1
            quote_content = "<br/>".join(quote_lines)
            result_parts.append(f"<blockquote><p>{quote_content}</p></blockquote>")
            continue

        # Bullet list: - item or * item
        if re.match(r"^\s*[-*]\s+", line):
            list_items: list[str] = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+(.+)$", lines[i]):
                match = re.match(r"^\s*[-*]\s+(.+)$", lines[i])
                if match:
                    item_text = _convert_inline_formatting(_escape_xml(match.group(1)))
                    list_items.append(f"<li>{item_text}</li>")
                i += 1
            result_parts.append(f"<ul>{''.join(list_items)}</ul>")
            continue

        # Numbered list: 1. item
        if re.match(r"^\s*\d+\.\s+", line):
            list_items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+(.+)$", lines[i]):
                match = re.match(r"^\s*\d+\.\s+(.+)$", lines[i])
                if match:
                    item_text = _convert_inline_formatting(_escape_xml(match.group(1)))
                    list_items.append(f"<li>{item_text}</li>")
                i += 1
            result_parts.append(f"<ol>{''.join(list_items)}</ol>")
            continue

        # Table: | col | col |
        if "|" in line and line.strip().startswith("|"):
            table_lines: list[str] = []
            while i < len(lines) and "|" in lines[i] and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            table_html = _convert_table(table_lines)
            result_parts.append(table_html)
            continue

        # Regular paragraph
        if line.strip():
            para_text = _convert_inline_formatting(_escape_xml(line))
            result_parts.append(f"<p>{para_text}</p>")

        i += 1

    return "".join(result_parts)


def _convert_table(lines: list[str]) -> str:
    """Convert markdown table to HTML table.

    Args:
        lines: List of markdown table lines.

    Returns:
        HTML table string.
    """
    if len(lines) < 2:
        return ""

    def parse_row(line: str) -> list[str]:
        """Parse a table row into cells."""
        # Remove leading/trailing pipes and split
        line = line.strip()
        if line.startswith("|"):
            line = line[1:]
        if line.endswith("|"):
            line = line[:-1]
        return [cell.strip() for cell in line.split("|")]

    # First row is header
    header_cells = parse_row(lines[0])

    # Second row is separator (skip it)
    # Remaining rows are body

    html_parts = ["<table><thead><tr>"]
    for cell in header_cells:
        cell_content = _convert_inline_formatting(_escape_xml(cell))
        html_parts.append(f"<th>{cell_content}</th>")
    html_parts.append("</tr></thead><tbody>")

    for line in lines[2:]:  # Skip header and separator
        cells = parse_row(line)
        html_parts.append("<tr>")
        for cell in cells:
            cell_content = _convert_inline_formatting(_escape_xml(cell))
            html_parts.append(f"<td>{cell_content}</td>")
        html_parts.append("</tr>")

    html_parts.append("</tbody></table>")
    return "".join(html_parts)


def storage_to_markdown(storage: str) -> str:
    """Convert Confluence storage format to markdown.

    Used when reading pages to provide readable output to the LLM.

    Args:
        storage: Confluence storage format XHTML.

    Returns:
        Markdown text.

    Example:
        >>> storage_to_markdown('<h1>Hello</h1><p>This is <strong>bold</strong>.</p>')
        '# Hello\\n\\nThis is **bold**.'
    """
    if not storage:
        return ""

    result = storage

    # Code blocks (structured macros) - handle first to preserve code content
    code_pattern = re.compile(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?'
        r'<ac:parameter[^>]*ac:name="language"[^>]*>([^<]*)</ac:parameter>.*?'
        r'<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?'
        r'</ac:structured-macro>',
        re.DOTALL | re.IGNORECASE,
    )
    result = code_pattern.sub(r"```\1\n\2\n```", result)

    # Also handle code macros without language parameter
    code_pattern_no_lang = re.compile(
        r'<ac:structured-macro[^>]*ac:name="code"[^>]*>.*?'
        r'<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>.*?'
        r'</ac:structured-macro>',
        re.DOTALL | re.IGNORECASE,
    )
    result = code_pattern_no_lang.sub(r"```\n\1\n```", result)

    # Headings
    for level in range(1, 7):
        result = re.sub(
            rf"<h{level}[^>]*>(.+?)</h{level}>",
            rf"{'#' * level} \1\n\n",
            result,
            flags=re.IGNORECASE | re.DOTALL,
        )

    # Bold
    result = re.sub(r"<strong>(.+?)</strong>", r"**\1**", result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r"<b>(.+?)</b>", r"**\1**", result, flags=re.IGNORECASE | re.DOTALL)

    # Italic
    result = re.sub(r"<em>(.+?)</em>", r"*\1*", result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r"<i>(.+?)</i>", r"*\1*", result, flags=re.IGNORECASE | re.DOTALL)

    # Strikethrough
    result = re.sub(r"<del>(.+?)</del>", r"~~\1~~", result, flags=re.IGNORECASE | re.DOTALL)
    result = re.sub(r"<s>(.+?)</s>", r"~~\1~~", result, flags=re.IGNORECASE | re.DOTALL)

    # Inline code
    result = re.sub(r"<code>(.+?)</code>", r"`\1`", result, flags=re.IGNORECASE | re.DOTALL)

    # Links
    result = re.sub(
        r'<a[^>]*href="([^"]+)"[^>]*>(.+?)</a>',
        r"[\2](\1)",
        result,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Images (Confluence format)
    result = re.sub(
        r'<ac:image[^>]*><ri:url[^>]*ri:value="([^"]+)"[^>]*/></ac:image>',
        r"![](\1)",
        result,
        flags=re.IGNORECASE,
    )

    # Horizontal rules
    result = re.sub(r"<hr\s*/?>", "\n---\n", result, flags=re.IGNORECASE)

    # Blockquotes
    result = re.sub(
        r"<blockquote[^>]*>(.+?)</blockquote>",
        lambda m: "\n".join("> " + line for line in _strip_html(m.group(1)).split("\n")),
        result,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Lists - unordered
    def convert_ul(match: re.Match[str]) -> str:
        """Convert unordered list to markdown."""
        content = match.group(1)
        items = re.findall(r"<li[^>]*>(.+?)</li>", content, re.IGNORECASE | re.DOTALL)
        return "\n".join(f"- {_strip_html(item).strip()}" for item in items) + "\n"

    result = re.sub(r"<ul[^>]*>(.+?)</ul>", convert_ul, result, flags=re.IGNORECASE | re.DOTALL)

    # Lists - ordered
    def convert_ol(match: re.Match[str]) -> str:
        """Convert ordered list to markdown."""
        content = match.group(1)
        items = re.findall(r"<li[^>]*>(.+?)</li>", content, re.IGNORECASE | re.DOTALL)
        return (
            "\n".join(f"{i+1}. {_strip_html(item).strip()}" for i, item in enumerate(items)) + "\n"
        )

    result = re.sub(r"<ol[^>]*>(.+?)</ol>", convert_ol, result, flags=re.IGNORECASE | re.DOTALL)

    # Tables
    def convert_table(match: re.Match[str]) -> str:
        """Convert HTML table to markdown."""
        content = match.group(0)

        # Extract header
        header_match = re.search(r"<thead[^>]*>(.+?)</thead>", content, re.IGNORECASE | re.DOTALL)
        if header_match:
            header_cells = re.findall(
                r"<th[^>]*>(.+?)</th>", header_match.group(1), re.IGNORECASE | re.DOTALL
            )
            header_row = "| " + " | ".join(_strip_html(cell).strip() for cell in header_cells) + " |"
            separator = "| " + " | ".join("---" for _ in header_cells) + " |"
        else:
            header_row = ""
            separator = ""

        # Extract body rows
        body_match = re.search(r"<tbody[^>]*>(.+?)</tbody>", content, re.IGNORECASE | re.DOTALL)
        body_rows: list[str] = []
        if body_match:
            rows = re.findall(r"<tr[^>]*>(.+?)</tr>", body_match.group(1), re.IGNORECASE | re.DOTALL)
            for row in rows:
                cells = re.findall(r"<td[^>]*>(.+?)</td>", row, re.IGNORECASE | re.DOTALL)
                body_rows.append(
                    "| " + " | ".join(_strip_html(cell).strip() for cell in cells) + " |"
                )

        parts = [p for p in [header_row, separator] + body_rows if p]
        return "\n".join(parts) + "\n"

    result = re.sub(r"<table[^>]*>.*?</table>", convert_table, result, flags=re.IGNORECASE | re.DOTALL)

    # Paragraphs
    result = re.sub(r"<p[^>]*>(.+?)</p>", r"\1\n\n", result, flags=re.IGNORECASE | re.DOTALL)

    # Line breaks
    result = re.sub(r"<br\s*/?>", "\n", result, flags=re.IGNORECASE)

    # Clean up remaining HTML tags
    result = _strip_html(result)

    # Unescape HTML entities
    result = html.unescape(result)

    # Clean up extra whitespace
    result = re.sub(r"\n{3,}", "\n\n", result)
    result = result.strip()

    return result


def _strip_html(text: str) -> str:
    """Remove HTML tags from text.

    Args:
        text: Text with HTML tags.

    Returns:
        Text with HTML tags removed.
    """
    return re.sub(r"<[^>]+>", "", text)


def extract_text_from_storage(storage: str) -> str:
    """Extract plain text from storage format (no formatting).

    Args:
        storage: Confluence storage format XHTML.

    Returns:
        Plain text with no formatting.
    """
    if not storage:
        return ""

    # Remove all tags
    text = _strip_html(storage)

    # Unescape HTML entities
    text = html.unescape(text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text)

    return text.strip()
