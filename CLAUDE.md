# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an MCP (Model Context Protocol) server that provides a semantic, AI-friendly interface to Washington State education assessment data. It's designed for school board members, district leaders, and analysts who want to ask meaningful questions about student performance trends and benchmark comparisons through AI conversation.

**Key Purpose**: This is an *analysis engine* meant to be used via AI (like Claude Desktop), not a dashboard or reporting tool. It wraps the state's public data APIs (data.wa.gov) and adds domain-aware query tools, consistent year handling, multi-district comparison sets, and ranking/trend analysis.

**Project Status**: Early development. APIs, schemas, and behavior may change. Currently optimized for analyzing a priority district against configurable comparison district sets.

## Development Setup

### Virtual Environment

Python virtual environment located in `.wa-ed-mcp/`:

- Python version: 3.14.2
- Activate on Windows: `.wa-ed-mcp\Scripts\activate`

### Environment Variables

Required in `.env`:

- `DATA_PORTAL_APP_TOKEN`: API token for data.wa.gov portal
- `ANTHROPIC_API_KEY`: Anthropic API key (may not be actively used)

### Running the Server

```bash
python server.py
```

The server uses stdio transport for MCP communication.

### Development Utilities

```bash
# Dump raw data from a named district set to a JSON file for offline testing
python dump_raw_data.py

# Debug enrollment tools and API connectivity
python debug.py
```

There is also a `test.py` (gitignored) for running ad-hoc test queries.

## Architecture

### File Structure

- **`server.py`**: Main MCP server — defines tools via `@mcp.tool()`, loads config and district XML at startup, contains all assessment query logic
- **`utils.py`**: Shared utilities — `load_config()`, `execute_query()`, `get_school_year()`, `get_school_year_from_string()`
- **`enrollment_tools.py`**: Enrollment-specific query functions; registered into MCP via `enrollment_tools.register_tools(mcp, config_data, execute_query)` in server.py
- **`wa-ed-config.json`**: All runtime configuration (see below)
- **`Districts.xml`**: Reference data mapping district codes to district names

### Configuration (`wa-ed-config.json`)

Key fields:
- `focus_district_id`: The primary district being analyzed (default: `"17414"` — LWSD)
- `latest_assessment_year`: Most recent year with data (currently 2025)
- `multidistrict_sets`: Named arrays of district IDs for comparison (DEFAULT, SMALL, MEDIUM, ONE). Used by `analyze_trends()`.
- `assessment_sets`: Maps each year to its specific data.wa.gov API endpoint URL
- `enrollment_sets`: Single endpoint covering all enrollment years

### MCP Tools (exposed via `@mcp.tool()`)

In `server.py`:
1. `get_district_scores()` — Raw scores for specified districts/grade/subject/year; aggregates across test types
2. `analyze_trends()` — Rankings + multi-year trends for a multidistrict set; **use this instead of computing rankings manually**
3. `get_district_name()` — District name lookup by ID
4. `list_multidistrict_sets()` — List available comparison sets
5. `get_multidistrict_set()` — Details of a specific comparison set
6. `list_available_assessment_years()` — All years with data
7. `list_available_tests()` — Test/subject/grade combos for a year
8. `list_available_student_groups()` — Available demographic groups

From `enrollment_tools` (registered at startup):
9. `get_available_enrollment_years()` — Years with enrollment data

### Internal (non-tool) Functions

- `get_multidistrict_scores()` — Fetches scores for all districts in a set across multiple years; called by `analyze_trends()`
- `get_district_rankings()` — Sorts and ranks districts by percent at grade level for a student group
- `get_annual_trends()` — Computes per-district trend rate between first and last year
- `execute_assessment_query()` — Resolves year → URL, then calls `execute_query()`

## Data Handling Quirks

**Column Name Changes Across Years** (handled in `get_district_scores()`):

| Year | Met-standard column | Total-students column | Suppression column |
|------|--------------------|-----------------------|-------------------|
| 2021 | `numeratorsuppressed` | `denominatorsuppressed` | `Suppression` |
| < 2023 (not 2021) | `countmetstandard` | `count_of_students_expected` | `Suppression` |
| 2023–2024 | `count_consistent_grade_level_knowledge_and_above` | `count_of_students_expected` | `DAT` |
| 2025+ | `count_consistent_grade_level` | `count_of_students_expected` | `DAT` |

All columns are aliased to consistent names in the SELECT so callers see uniform field names.

**2021 COVID Grade Shift**: The 2020-21 test was given in fall 2021. Students are listed one grade higher than their test grade level. `get_district_scores()` increments `grade` by 1 when querying year 2021 to compensate.

**2020 Skipped**: No state testing occurred. `get_multidistrict_scores()` skips year 2020 automatically.

**Student Group Name Variants**: "Two or More Races" appears as both `TwoorMoreRaces` and `Two Or More Races` across years. `get_district_scores()` adds both variants to the query and normalizes to `"Two Or More Races"` in output.

**NULL Handling**: The portal returns string `"NULL"` for missing data; code converts to `"0"` before integer conversion.

**Data Aggregation**: Districts may have multiple test-type records (SBAC, WA-AIM, WCAS) per subject/grade. `get_district_scores()` sums student counts across all test types before computing percentages.

## Query Construction

Queries use SoQL (Socrata Query Language) sent to data.wa.gov's JSON API:
- `caseless_eq()` for single-value filters, `caseless_one_of()` for list filters
- Grade levels formatted as two-digit strings (`"03"` not `"3"`)
- Years converted to school year format via `get_school_year()` (e.g., 2025 → `"2024-25"`)
- Lists passed as `"val1","val2"` strings (no brackets) using `get_list_as_string()`

## Adding New Tools

- Decorate with `@mcp.tool()` — the docstring becomes the tool's description for the AI
- `district_ids`, `tests`, and `student_groups` parameters are lists even for single values
- For tools in separate modules, follow the `enrollment_tools.register_tools(mcp, config_data, execute_query)` pattern
- Check error returns with `if "error" in response` before processing results
