import sys
import asyncio
from .config_loader import load_config
from .data_fetcher import fetch_all_data
from .data_transformer import transform_data
from .report_generator import generate_report


async def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else None

    print("=== ADO Report Agent (Python) ===\n")

    print("Loading configuration...")
    config = load_config(config_path)

    print(f"Connecting to ADO: {config.ado_organization}/{config.ado_project}")
    print("Fetching work items via MCP server...")
    raw_data = await fetch_all_data(config)
    print(f"Fetched {len(raw_data)} work items\n")

    if not raw_data:
        print("No work items found matching the query. Report will show empty state.")

    print("Transforming data and computing progress...")
    report = transform_data(raw_data, config)
    phase_names = ", ".join(p.display_name for p in report.phases)
    print(f"Phases: {phase_names}")
    print(f"Overall progress: {report.summary.overall_progress_percent}%\n")

    print("Generating interactive HTML report via Claude Code...")
    report_path = generate_report(report, config)

    print(f"\nReport generated successfully: {report_path}")
    print(f"Open it in your browser: file://{report_path}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as err:
        msg = str(err)
        print(f"\nAgent failed: {msg}", file=sys.stderr)

        if "401" in msg or "Unauthorized" in msg:
            print(
                "\nHint: Your ADO PAT may be expired or invalid. Generate a new one at:",
                file=sys.stderr,
            )
            print(
                "  https://dev.azure.com/YOUR_ORG/_usersSettings/tokens",
                file=sys.stderr,
            )

        if "ENOENT" in msg and "claude" in msg:
            print(
                "\nHint: Claude CLI not found. Make sure it is installed and in your PATH.",
                file=sys.stderr,
            )
            print("  Run: claude --version", file=sys.stderr)

        sys.exit(1)
