# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run all tests
uv run pytest tests/ -v

# Run a single test file
uv run pytest tests/test_validation.py -v

# Run a single test
uv run pytest tests/test_validation.py::TestCqlValidation::test_valid_cql_queries -v

# Lint
uv run ruff check src/

# Format
uv run ruff format src/

# Run the server
uv run fast-mcp-confluence
# or: uv run python -m fast_mcp_confluence
```

## Architecture

This is a FastMCP server providing 45 tools for Confluence Cloud API access.

### Layer Structure

```
__main__.py          → Entry point, server startup
server.py            → FastMCP instance, service initialization
config.py            → Pydantic settings, SSRF protection
├── services/
│   ├── confluence_client.py  → HTTP client, rate limiting, auth
│   └── cache.py              → SQLite cache with TTL, encryption
├── tools/           → 10 modules, each registers tools with @mcp.tool()
│   ├── pages.py, spaces.py, comments.py, attachments.py
│   ├── labels.py, properties.py, watchers.py, metadata.py
│   ├── bulk.py, cache.py
└── utils/
    ├── validation.py      → Pydantic input validators, XSS sanitization
    └── storage_format.py  → Markdown ↔ Confluence XHTML conversion
```

### Key Patterns

**Tool Registration**: Tools are decorated with `@mcp.tool()` and import the global `confluence` client and `cache` service from `server.py`.

**Input Validation**: All user inputs go through Pydantic models in `validation.py` (e.g., `SpaceKeyInput`, `CqlInput`, `AttachmentInput`). Use `validate_*()` functions or instantiate models directly.

**Response Building**: All tools return `build_response(success, **data)` which sanitizes output for XSS.

**Markdown Conversion**: Content goes through `markdown_to_storage()` on write and `storage_to_markdown()` on read (`utils/storage_format.py`).

### Security Controls

- **SSRF**: `config.py` blocks private IPs and validates hostnames against allowlist
- **CQL Injection**: `validation.py` blocks dangerous patterns in CQL queries
- **Rate Limiting**: Token bucket in `confluence_client.py`, auth lockout in `auth.py`
- **Cache Privacy**: `cache.py` filters sensitive fields before storing

### Configuration

All settings via environment variables or `.env` file. Key settings:
- `CONFLUENCE_URL`, `CONFLUENCE_EMAIL`, `CONFLUENCE_API_TOKEN` (required)
- `MCP_API_KEY` (enables endpoint authentication)
- `CACHE_ENCRYPTION_ENABLED`, `CACHE_ENCRYPTION_KEY` (cache encryption)
