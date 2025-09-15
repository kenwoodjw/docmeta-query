# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Dify Plugin** that provides document metadata querying capabilities across multiple datasets. The plugin is structured as a Python-based tool provider that integrates with Dify's plugin ecosystem.

## Architecture

### Core Components

- **Plugin Entry Point**: `main.py` - Simple entry point that initializes the Dify plugin
- **Tool Provider**: `provider/docmeta-query.py` - Contains `DocmetaQueryProvider` class for credential validation
- **Tool Implementation**: `tools/docmeta-query.py` - Contains `DocmetaQueryTool` class with the main query logic
- **Configuration Files**:
  - `manifest.yaml` - Main plugin manifest defining metadata, permissions, and runtime configuration
  - `provider/docmeta-query.yaml` - Tool provider definition and schema
  - `tools/docmeta-query.yaml` - Tool specification with parameters and descriptions

### Plugin Type
This is a **Tool** type plugin that extends Dify with document metadata querying capabilities. It can query multiple datasets by document name and return filtered metadata.

## Development Commands

### Setup
```bash
# Install dependencies (Python 3.12 required)
pip install -r requirements.txt
```

### Testing & Debugging
```bash
# Run the plugin locally for debugging
python -m main
```

**Environment Configuration**: Copy `.env.example` to `.env` and configure:
- `INSTALL_METHOD=remote`
- `REMOTE_INSTALL_URL=debug.dify.ai` (or your Dify instance)
- `REMOTE_INSTALL_PORT=5003`
- `REMOTE_INSTALL_KEY=your-debug-key`

### Packaging
```bash
# Package the plugin (requires dify-plugin CLI tool)
dify-plugin plugin package ./
```

### Publishing
- **Automated**: GitHub Actions workflow triggers on release creation
- **Manual**: Package and submit the `.difypkg` file to Dify Marketplace

## Key Implementation Details

### Tool Parameters
The tool accepts these parameters:
- `dataset_list`: List of dataset IDs (supports JSON array, comma-separated string)
- `kb_api_key`: API key for knowledge base authentication
- `kb_base_url`: Optional base URL (defaults to http://127.0.0.1:5001)
- `document_name`: Keyword for document name matching
- `metadata_filter`: Optional filter for metadata (JSON array/object or comma-separated names)

### Metadata Filtering
- Built-in metadata is excluded by default (`document_name`, `uploader`, `upload_date`, etc.)
- Supports inclusion filtering by name or name-value pairs
- Handles various input formats (JSON, comma-separated, key=value pairs)

### Error Handling
- Per-dataset error isolation (one dataset failure doesn't stop others)
- Comprehensive input validation with descriptive error messages
- HTTP request timeout of 30 seconds

## File Structure
```
├── main.py                          # Plugin entry point
├── manifest.yaml                    # Plugin manifest
├── requirements.txt                 # Python dependencies
├── provider/
│   ├── docmeta-query.yaml          # Provider configuration
│   └── docmeta-query.py            # Provider implementation
└── tools/
    ├── docmeta-query.yaml          # Tool specification
    └── docmeta-query.py            # Tool implementation
```

## Dependencies
- `dify_plugin>=0.2.0,<0.3.0` - Core Dify plugin SDK
- `requests>=2.31.0,<3` - HTTP client for API calls

## GitHub Actions
The repository includes an automated publishing workflow that:
1. Triggers on GitHub releases
2. Packages the plugin using the Dify CLI
3. Creates PR to the dify-plugins repository
4. Requires `PLUGIN_ACTION` secret with repository write permissions