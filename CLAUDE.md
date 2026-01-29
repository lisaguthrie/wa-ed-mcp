# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an MCP (Model Context Protocol) server that provides a semantic, AI-friendly interface to Washington State education assessment data. It's designed for school board members, district leaders, and analysts who want to ask meaningful questions about student performance trends and benchmark comparisons through AI conversation.

**Key Purpose**: This is an *analysis engine* meant to be used via AI (like Claude Desktop), not a dashboard or reporting tool. It wraps the state's public data APIs and adds domain-aware query tools, consistent year handling, benchmark district sets, and ranking/trend analysis.

**Typical Use Cases**:

- "Show the benchmark ranking for 3rd grade ELA (All Students) in 2025"
- "How has LWSD's benchmark ranking changed over time?"
- "Which districts overtook us last year, and why?"
- "Are any benchmark districts on a strong upward trajectory?"

**Project Status**: Early development. APIs, schemas, and behavior may change. Currently optimized for analyzing a priority district against configurable benchmark districts.

## Development Setup

### Virtual Environment

The project uses a Python virtual environment located in `.wa-ed-mcp/`:

- Python version: 3.14.2
- Activate on Windows: `.wa-ed-mcp\Scripts\activate`
- Activate on Unix/Mac: `source .wa-ed-mcp/bin/activate`

### Environment Variables

Required environment variables in `.env`:

- `DATA_PORTAL_APP_TOKEN`: API token for data.wa.gov portal
- `ANTHROPIC_API_KEY`: Anthropic API key (may not be actively used)

### Running the Server

```bash
python server.py
```

The server runs with stdio transport, which is typical for MCP servers that communicate via standard input/output.

### Testing

Run test queries with:

```bash
python test.py
```

## Architecture

### Core Components

**server.py**: Main MCP server implementation

- Uses FastMCP framework to define MCP tools
- Loads configuration from `wa-ed-config.json` on startup
- Loads district mappings from `Districts.xml` on startup
- Provides 8 MCP tools for querying and analyzing education data

**wa-ed-config.json**: Configuration file defining:

- `primary_district_id`: Default district (17414)
- `latest_assessment_year`: Most recent assessment year (2025)
- `benchmark_sets`: Named sets of districts for comparison (DEFAULT, SMALL, MEDIUM)
- `assessment_sets`: Year-to-URL mappings for data.wa.gov API endpoints

**Districts.xml**: Reference data mapping district codes to district names

### MCP Tools

The server exposes these tools:

1. `get_district_scores()`: Retrieve test scores for specified districts, grades, subjects, and student groups
2. `get_benchmark_scores()`: Get scores for a benchmark set across multiple years
3. `analyze_benchmark_trends()`: Analyze trends and rankings for benchmark districts over time
4. `get_district_name()`: Look up district name by ID
5. `list_benchmark_sets()`: List available benchmark district sets
6. `list_available_years()`: List all available assessment years
7. `list_available_tests()`: List test/subject/grade combinations for a given year
8. `list_available_student_groups()`: List available student demographic groups

### Data Handling Quirks

The Washington State OSPI portal has inconsistencies across years that the code handles:

**Column Name Changes**:

- Years < 2023: `countmetstandard` column for students meeting standard
- Years 2023-2024: `count_consistent_grade_level_knowledge_and_above`
- Year 2025+: `count_consistent_grade_level`
- Suppression column changed from `Suppression` to `DAT` starting in 2023

**Data Aggregation**:
The `get_district_scores()` function aggregates results across multiple test types (SBAC, WA-AIM, WCAS) since districts may have students taking different assessments for the same subject. Student counts are summed before calculating percentages.

**NULL Handling**:
The portal returns string "NULL" for missing data, which the code converts to "0" before integer conversion.

### Query Construction

The server constructs SoQL (Socrata Query Language) queries for the data.wa.gov API:

- Uses URL encoding via `urllib.parse.quote()`
- Applies filters using `caseless_eq()` and `caseless_one_of()` functions
- Formats grade levels as two-digit strings (e.g., "03" for grade 3)
- Converts years to school year format (e.g., 2025 → "2024-25")

## Key Implementation Patterns

### Error Handling

Functions return dictionaries with an "error" key when errors occur, making it easy for callers to check `if "error" in response`.

### Configuration-Driven URLs

Different assessment years use different dataset URLs on data.wa.gov. The `assessment_sets` configuration maps years to their corresponding API endpoints.

### Ranking Algorithm

`analyze_benchmark_trends()` sorts districts by `percent_consistent_grade_level` in descending order, with None values sorting to the end. Rankings are assigned sequentially starting from 1.

## Modifying the Code

When adding new tools or modifying queries:

- Use the `@mcp.tool()` decorator on functions you want to expose
- Include clear docstrings as they become part of the tool description
- Test with multiple years to ensure column name handling is correct
- Remember that district_ids, tests, and student_groups are lists even when querying single values
- Consider data aggregation needs when a district might have multiple test records for the same query
