# Claude Code User Guide for Confluence

A comprehensive guide to using Claude Code with the Confluence MCP server.

## Table of Contents

1. [Introduction](#introduction)
2. [Prerequisites](#prerequisites)
3. [Triggering the Skill](#triggering-the-skill)
4. [Common Tasks](#common-tasks)
5. [CQL Query Cookbook](#cql-query-cookbook)
6. [Working with Markdown](#working-with-markdown)
7. [Best Practices](#best-practices)
8. [Troubleshooting](#troubleshooting)
9. [Advanced Workflows](#advanced-workflows)

---

## Introduction

The Confluence skill provides access to 45 MCP tools for managing Confluence Cloud content. You can:

- Create, update, and organize documentation
- Search across spaces and pages
- Manage page hierarchies, labels, and attachments
- Perform bulk operations for migrations
- Cache management for performance

**Key Feature:** Write content in markdown - automatic conversion to/from Confluence storage format.

---

## Prerequisites

### 1. MCP Server Running

Start the server:

```bash
fast-mcp-confluence
# or
python -m fast_mcp_confluence
```

### 2. Configuration

Ensure these environment variables are set:

```env
CONFLUENCE_URL=mycompany.atlassian.net
CONFLUENCE_EMAIL=your-email@example.com
CONFLUENCE_API_TOKEN=your-api-token
```

### 3. API Token

Get a token from: https://id.atlassian.com/manage-profile/security/api-tokens

---

## Triggering the Skill

### Automatic Triggers

The skill activates automatically when you mention:

- "search Confluence"
- "create a page"
- "update documentation"
- "manage Confluence spaces"
- "add comments"
- "upload attachments"
- "manage labels"
- "find pages"
- "organize documentation"
- "bulk update pages"

### Example Prompts

```
"Create a new page in DOCS called 'API Guide'"

"Search Confluence for pages about authentication"

"Add the 'reviewed' label to page 12345"

"Find all pages modified in the last week"

"Move page 67890 under parent 12345"
```

---

## Common Tasks

### Creating Documentation Pages

**Simple page:**
```
"Create a page in DOCS space titled 'Getting Started' with a welcome message"
```

**Page with hierarchy:**
```
"Create a child page under 12345 called 'API Reference'"
```

**Page with labels:**
```
"Create a page in DOCS called 'Security Guide' and add labels: security, compliance"
```

### Searching Content

**By text:**
```
"Find all pages mentioning 'authentication'"
```

**By space:**
```
"List all pages in the DOCS space"
```

**By label:**
```
"Find pages with the 'api' label"
```

**Recent changes:**
```
"Show pages modified in the last 7 days"
```

### Updating Pages

**Update content:**
```
"Update page 12345 with the new API documentation I've prepared"
```

**Change title:**
```
"Rename page 12345 to 'API Reference v2'"
```

### Managing Page Hierarchies

**View structure:**
```
"Show the child pages under 12345"
```

**Reorganize:**
```
"Move page 67890 to be a child of 12345"
```

### Working with Labels

**Add labels:**
```
"Add 'documentation' and 'public' labels to page 12345"
```

**Search by label:**
```
"Find all pages with the 'needs-review' label"
```

**Remove label:**
```
"Remove the 'draft' label from page 12345"
```

### Bulk Operations

**Update multiple pages:**
```
"Update pages 123, 456, and 789 to have the title prefix 'Archive: '"
```

**Add labels to multiple pages:**
```
"Add the 'deprecated' label to pages 123, 456, 789"
```

**Archive multiple pages:**
```
"Archive pages 123, 456, and 789"
```

---

## CQL Query Cookbook

### Basic Queries

| Goal | CQL Query |
|------|-----------|
| All pages in space | `type=page AND space=DOCS` |
| Title contains text | `title~"API Guide"` |
| Full-text search | `text~"authentication"` |
| Has specific label | `label=important` |

### Date-Based Queries

| Goal | CQL Query |
|------|-----------|
| Created last 7 days | `created>=now("-7d")` |
| Modified last 24 hours | `lastmodified>=now("-24h")` |
| Created this month | `created>=startOfMonth()` |
| Created this year | `created>=startOfYear()` |

### Label-Based Queries

| Goal | CQL Query |
|------|-----------|
| Single label | `label=api` |
| Multiple labels (AND) | `label=api AND label=public` |
| Multiple labels (OR) | `label=important OR label=urgent` |
| Exclude label | `NOT label=draft` |

### Combined Queries

**Documentation needing review:**
```cql
type=page AND space=DOCS AND label=needs-review AND lastmodified<=now("-30d")
```

**Recent API documentation:**
```cql
type=page AND label=api AND created>=now("-7d")
```

**Meeting notes from specific space:**
```cql
type=page AND space=TEAM AND title~"Meeting Notes"
```

**Draft pages by current user:**
```cql
type=page AND label=draft AND creator=currentUser()
```

---

## Working with Markdown

### Supported Features

| Feature | Syntax |
|---------|--------|
| Bold | `**text**` |
| Italic | `*text*` |
| Headers | `# H1`, `## H2`, `### H3` |
| Links | `[text](url)` |
| Images | `![alt](url)` |
| Code inline | `` `code` `` |
| Code block | ` ```language ... ``` ` |
| Lists | `- item` or `1. item` |
| Tables | Pipe-delimited |
| Blockquotes | `> text` |
| Horizontal rule | `---` |

### Markdown Tables

```markdown
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |
| Data 4   | Data 5   | Data 6   |
```

### Code Blocks

````markdown
```python
def hello():
    print("Hello, World!")
```
````

### Tips

1. **Use headers for structure** - Confluence converts them to proper heading styles
2. **Tables work well** - Automatic conversion to Confluence tables
3. **Code blocks preserve formatting** - Syntax highlighting included
4. **Links remain clickable** - External URLs work as expected

---

## Best Practices

### Page Organization

1. **Use consistent naming conventions**
   - `Feature: [Name]` for features
   - `Guide: [Topic]` for guides
   - `RFC: [Proposal]` for RFCs

2. **Create logical hierarchies**
   - Top-level space home page
   - Category pages as parents
   - Detail pages as children

3. **Use labels systematically**
   - `api` for API documentation
   - `needs-review` for pending reviews
   - `archived` for old content

### Label Conventions

| Category | Labels |
|----------|--------|
| Status | `draft`, `reviewed`, `published`, `deprecated` |
| Type | `guide`, `reference`, `tutorial`, `api` |
| Audience | `internal`, `public`, `team-only` |
| Version | `v1`, `v2`, `current` |

### When to Use Bulk Operations

- Migrations from other systems
- Applying consistent labels across many pages
- Archiving old documentation
- Reorganizing page hierarchies

### Cache Management

- Cache helps with repeated queries
- Invalidate after bulk changes
- Clear specific categories when needed:
  ```
  "Clear the spaces cache"
  "Invalidate the metadata cache"
  ```

---

## Troubleshooting

### Common Errors

#### "Space key must start with a letter"

**Problem:** Invalid space key format

**Solution:** Use uppercase, start with letter
```
Wrong: docs, 2024-docs, my-space
Right: DOCS, DOCS2024, MY_SPACE
```

#### "Page ID must be numeric"

**Problem:** Non-numeric page ID

**Solution:** Use only digits
```
Wrong: page-123, abc
Right: 12345
```

#### "Label must be lowercase"

**Problem:** Mixed case or invalid characters

**Solution:** Use lowercase with hyphens
```
Wrong: MyLabel, my label, my.label
Right: my-label, mylabel, my_label
```

#### "CQL contains dangerous characters"

**Problem:** Query has blocked patterns

**Solution:** Remove these patterns:
- `;` (semicolons)
- `--` (double dash)
- `/*` or `*/` (block comments)

#### "File type not allowed"

**Problem:** Blocked file extension

**Solution:** Avoid these extensions:
- `.exe`, `.bat`, `.cmd`, `.sh`, `.ps1`, `.dll`, `.so`

### CQL Query Debugging

1. **Start simple** - Basic query first, add conditions
2. **Check quotes** - Strings with spaces need quotes
3. **Verify operators** - Use `~` for contains, `=` for exact
4. **Test incrementally** - Add one condition at a time

### Rate Limiting

If you get rate limit errors:
1. Wait before retrying
2. Reduce bulk operation batch sizes
3. Add delays between operations

---

## Advanced Workflows

### Documentation Site Setup

**Step 1: Create the space**
```
"Create a space with key DOCS and name 'Documentation'"
```

**Step 2: Create the home page**
```
"Create a page in DOCS called 'Documentation Home' with navigation links"
```

**Step 3: Create category pages**
```
"Create pages under the home page for: Getting Started, API Reference, Guides"
```

**Step 4: Add content pages**
```
"Create detail pages under each category"
```

### Meeting Notes Automation

**Creating meeting notes:**
```
"Create a page in TEAM space called 'Meeting Notes - 2024-01-15' with:
- Attendees section
- Agenda section
- Action items section
Add labels: meeting-notes, team-sync"
```

**Finding recent meetings:**
```
"Search for pages with title containing 'Meeting Notes' created in the last 30 days"
```

### Knowledge Base Organization

**Tagging strategy:**
```
"Add these labels to page 12345: topic-authentication, audience-developers, status-current"
```

**Content audit:**
```
"Find all pages in DOCS that were last modified more than 90 days ago"
```

**Migration workflow:**
```
1. "Find all pages with label 'legacy'"
2. "Add label 'migrated' to those pages"
3. "Archive pages with both 'legacy' and 'migrated' labels"
```

### API Documentation Workflow

**Create API reference structure:**
```
"Create parent page 'API v2 Reference' in DOCS"
"Create child pages: Endpoints, Authentication, Error Codes, Examples"
```

**Version management:**
```
"Add label 'v2' to page 12345"
"Remove label 'current' from pages with label 'v1'"
"Add label 'current' to pages with label 'v2'"
```

### Content Review Process

**Flag for review:**
```
"Add 'needs-review' label to page 12345"
```

**Find pending reviews:**
```
"Search for pages with label 'needs-review' in DOCS space"
```

**Mark reviewed:**
```
"Remove 'needs-review' and add 'reviewed' label to page 12345"
```

---

## Quick Reference

### Most Used Commands

| Task | Example Prompt |
|------|----------------|
| Create page | "Create a page in DOCS called 'Title'" |
| Update page | "Update page 12345 with new content" |
| Search | "Find pages about authentication" |
| Add label | "Add 'important' label to page 12345" |
| Move page | "Move page 67890 under 12345" |
| Get children | "Show children of page 12345" |
| Bulk label | "Add 'archived' to pages 123, 456, 789" |

### Space Key Format

- Uppercase letters
- Numbers allowed (not first character)
- Underscores allowed
- Example: `DOCS`, `API_V2`, `TEAM1`

### Label Format

- Lowercase letters
- Numbers allowed
- Hyphens and underscores allowed
- Example: `api`, `needs-review`, `v2_docs`

### Page ID Format

- Numbers only
- Example: `12345`, `98765`

---

## Additional Resources

- **SKILL.md** - Core skill documentation
- **references/cql-guide.md** - Complete CQL documentation
- **references/tool-reference.md** - All 45 tools with signatures
- **references/validation-rules.md** - Input validation details
