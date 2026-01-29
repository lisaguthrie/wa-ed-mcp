# WA Education Data MCP Server

An MCP (Model Context Protocol) server that provides AI-friendly access to Washington State education assessment data.

## What it does

This server connects to the Washington State data.wa.gov portal and exposes tools for querying standardized test scores across districts, student groups, grades, and years. It's designed to be used with Claude Desktop or other MCP clients for conversational data analysis.

Key features:

- Query district assessment scores (SBAC, WA-AIM, WCAS)
- Compare districts against benchmark sets
- Analyze trends and rankings over time
- Handle year-to-year data schema inconsistencies

## Setup

1. Create a virtual environment:

```bash
python -m venv .wa-ed-mcp
.wa-ed-mcp\Scripts\activate  # Windows
source .wa-ed-mcp/bin/activate  # Mac/Linux
```

2. Install dependencies:

```bash
pip install mcp fastmcp requests python-dotenv
```

3. Create a `.env` file with your data.wa.gov API token:

```
DATA_PORTAL_APP_TOKEN=your_token_here
```

4. Run the server:

```bash
python server.py
```

## Connecting to Claude Desktop

Add to your Claude Desktop MCP settings:

```json
{
  "mcpServers": {
    "wa-education": {
      "command": "C:\\path\\to\\.wa-ed-mcp\\Scripts\\python.exe",
      "args": ["C:\\path\\to\\wa-ed-mcp\\server.py"]
    }
  }
}
```

Restart Claude Desktop to load the server.

## Configuration

Edit `wa-ed-config.json` to configure:

- Primary district ID
- Benchmark district sets
- Assessment year mappings to data portal URLs

## Available Tools

- `get_district_scores()` - Get test scores for specified districts
- `get_benchmark_scores()` - Get scores for a benchmark set across years
- `analyze_benchmark_trends()` - Analyze ranking trends over time
- `get_district_name()` - Look up district names
- `list_benchmark_sets()` - List configured benchmark sets
- `list_available_years()` - List available assessment years
- `list_available_tests()` - List test/subject/grade combinations
- `list_available_student_groups()` - List demographic groups

## Project Status

Early development. The focus is on benchmark district comparisons and trend analysis for supporting education decision-making.
