# Fast MCP Confluence

A production-ready MCP (Model Context Protocol) server for Atlassian Confluence Cloud.

## Features

- **Full Confluence Cloud API v2 support**
- **Markdown input/output** - Write content in markdown, automatically converted to/from Confluence storage format
- **SQLite caching** with TTL-based expiration and optional encryption
- **Rate limiting** with token bucket algorithm
- **Security hardening** - Input validation, XSS sanitization, SSRF prevention
- **Structured logging** with JSON output for production

## Installation

```bash
# Install from source
pip install -e .

# With development dependencies
pip install -e ".[dev]"

# With cache encryption support
pip install -e ".[encryption]"
```

## Configuration

Create a `.env` file or set environment variables:

```env
# Required
CONFLUENCE_URL=mycompany.atlassian.net
CONFLUENCE_EMAIL=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token

# Optional
MCP_HOST=127.0.0.1
MCP_PORT=5463
LOG_LEVEL=INFO
LOG_FORMAT=console  # or "json" for production

# MCP endpoint authentication (recommended for production)
MCP_API_KEY=your-secure-api-key

# Cache configuration
CACHE_ENABLED=true
CACHE_DB_PATH=~/.fast-mcp-confluence/cache.db
```

### Getting a Confluence API Token

1. Go to https://id.atlassian.com/manage-profile/security/api-tokens
2. Click "Create API token"
3. Copy the token and set it as `CONFLUENCE_API_TOKEN`

## Usage

### Start the Server

```bash
# Using the installed script
fast-mcp-confluence

# Or using Python module
python -m fast_mcp_confluence
```

### Available Tools (45 Tools)

#### Spaces (6 tools)
- `get_spaces` - List all spaces
- `get_space` - Get space by ID
- `get_space_by_key` - Get space by key
- `create_space` - Create a new space
- `update_space` - Update space details
- `delete_space` - Delete a space

#### Pages (9 tools)
- `create_page` - Create a new page with markdown content
- `get_page` - Get page by ID (returns markdown)
- `get_page_by_title` - Get page by space and title
- `update_page` - Update page title or content
- `delete_page` - Delete a page
- `get_page_children` - Get child pages
- `move_page` - Move page to new parent
- `get_page_versions` - Get version history
- `search_pages` - Search using CQL

#### Comments (5 tools)
- `add_footer_comment` - Add a comment to a page
- `get_footer_comments` - Get comments on a page
- `update_comment` - Update an existing comment
- `delete_comment` - Delete a comment
- `get_comment_versions` - Get comment version history

#### Attachments (5 tools)
- `get_attachments` - List attachments on a page
- `get_attachment` - Get attachment metadata
- `add_attachment` - Upload an attachment
- `delete_attachment` - Delete an attachment
- `download_attachment` - Get attachment download URL

#### Labels (4 tools)
- `get_page_labels` - Get labels on a page
- `add_page_labels` - Add labels to a page
- `remove_page_label` - Remove a label from a page
- `get_space_labels` - Get labels in a space

#### Content Properties (4 tools)
- `get_content_properties` - Get all properties on a page
- `get_content_property` - Get a specific property
- `set_content_property` - Create or update a property
- `delete_content_property` - Delete a property

#### Watchers (3 tools)
- `get_page_watchers` - Get watchers on a page
- `add_page_watch` - Add current user as watcher
- `remove_page_watch` - Remove current user as watcher

#### Bulk Operations (3 tools)
- `bulk_update_pages` - Update multiple pages in parallel
- `bulk_add_labels` - Add labels to multiple pages
- `bulk_delete_pages` - Delete multiple pages

#### Metadata (4 tools)
- `get_content_types` - Get available content types (cached)
- `search_users` - Search for users
- `get_current_user` - Get current authenticated user
- `get_space_permissions` - Get space permission types

#### Cache Management (2 tools)
- `get_cache_stats` - Get cache statistics
- `invalidate_cache` - Clear cache entries

### Example Usage with Claude

```
User: Create a new page in the DOCS space called "API Guide"

Claude: I'll create that page for you.
[Uses create_page tool with space_key="DOCS", title="API Guide", body="# API Guide\n\n..."]

User: Search for all pages about authentication

Claude: Let me search for those pages.
[Uses search_pages tool with cql='text~"authentication"']
```

### CQL Query Examples

CQL (Confluence Query Language) is used for searching:

```
# All pages in a space
type=page AND space=MYSPACE

# Pages with title containing text
title~"meeting notes"

# Pages with specific label
label=important

# Pages created in last 7 days
created>=now("-7d")

# Pages under a specific parent
ancestor=12345

# Combined queries
type=page AND space=DOCS AND label=api AND created>=now("-30d")
```

## Development

### Running Tests

```bash
pytest tests/
```

### Code Style

```bash
ruff check src/
ruff format src/
```

## Architecture

This server follows the MCP Server Reference Architecture with:

- **Pydantic Settings** for configuration management
- **AsyncIO** throughout for high performance
- **Token bucket** rate limiting
- **SQLite caching** with optional SQLCipher encryption
- **Bleach** HTML sanitization for XSS prevention
- **Structured logging** with sensitive data redaction

## Security Features

- **SSRF Prevention** - Private IP blocking, hostname allowlist
- **Input Validation** - All user inputs validated before use
- **XSS Prevention** - HTML sanitization with allowlist approach
- **Timing-Safe Auth** - HMAC comparison prevents timing attacks
- **Rate Limiting** - Token bucket + auth failure lockout
- **Cache Security** - Sensitive field filtering, optional encryption

## License

MIT
