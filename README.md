# ADO Report Agent

Automates the generation of interactive HTML progress reports from Azure DevOps (ADO) work items.

## How It Works

1. Connects to ADO via a custom MCP server using PAT authentication
2. Retrieves work items (and their child tasks) using a configurable WIQL query
3. Groups work items by tags that represent project phases
4. Calculates progress percentages per work item, per phase, and overall
5. Uses Claude Code (CLI) to generate a polished, interactive HTML report

## Prerequisites

| Requirement      | Version / Details                                    |
|------------------|------------------------------------------------------|
| Python           | >= 3.11                                              |
| Claude CLI       | Latest (`claude` command available and authenticated) |
| Azure DevOps PAT | Scopes: `Work Items (Read)` at minimum               |

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `mcp` — Model Context Protocol SDK (server + client)
- `pyyaml` — YAML configuration parsing
- `httpx` — Async HTTP client for ADO API calls

### 2. Configure

Edit `config/report-config.yaml` with your:
- ADO organization URL and project name
- Personal Access Token (PAT) — can be set directly or as an env var name
- WIQL query to select work items
- Phase tags for grouping
- Report output settings
- Task state mappings

### 3. Set PAT

You can either put the PAT directly in `config/report-config.yaml` under `ado.pat_env_var` (if 40+ characters, it's treated as the token itself), or set an environment variable:

```bash
# Option A: Set PAT directly in config (pat_env_var field)
# Option B: Use an environment variable
export ADO_PAT="your-personal-access-token-here"
# Then set pat_env_var: "ADO_PAT" in the config
```

### 4. Verify Claude CLI

```bash
claude --version
claude --print "Hello"   # Should return a response without auth errors
```

## Usage

```bash
# Run the full pipeline from the project root
python -m agent-py

# With a custom config path
python -m agent-py /path/to/custom-config.yaml

# Or use the convenience script
python run.py
```

The generated HTML report will be saved to the `output/` directory (configurable).

## Project Structure

```
ado-report-agent/
├── config/
│   └── report-config.yaml        # User-editable configuration
├── mcp-server-py/                # MCP Server for ADO (Python)
│   ├── __main__.py               # Server entry point
│   ├── server.py                 # MCP tool registration
│   └── ado_client.py             # ADO REST API wrapper (httpx)
├── agent-py/                     # Orchestrator Agent (Python)
│   ├── __main__.py               # Agent entry point
│   ├── config_loader.py          # YAML config parser
│   ├── data_fetcher.py           # MCP client data fetcher
│   ├── data_transformer.py       # Progress computation
│   ├── report_generator.py       # Claude Code invocation
│   └── claude_code.py            # Claude Code CLI wrapper
├── templates/
│   └── report-prompt.md          # Prompt template reference
├── requirements.txt              # Python dependencies
├── run.py                        # Convenience entry point
└── output/                       # Generated reports
```

## MCP Server Tools

The MCP server exposes four tools:

| Tool                     | Description                                      |
|--------------------------|--------------------------------------------------|
| `ado_execute_wiql`       | Run a WIQL query and return matching work item IDs |
| `ado_get_work_item`      | Fetch a single work item with relations           |
| `ado_get_work_item_tasks`| Get all child tasks of a parent work item         |
| `ado_get_work_items_batch`| Bulk fetch multiple work items by IDs            |

## Progress Calculation

- **Work item progress** = completed tasks / total tasks
- **Phase progress** = completed tasks / total tasks across all work items in the phase
- **Overall progress** = average of all phase progress percentages (only phases with tasks)
