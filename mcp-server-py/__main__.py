import os
import sys
from .ado_client import AdoClient
from .server import create_server


def main():
    org_url = os.environ.get("ADO_ORG_URL")
    project = os.environ.get("ADO_PROJECT")

    # ADO_PAT_ENV_VAR can be either an env var name or the PAT token directly.
    # If it looks like a token (40+ chars), use it directly; otherwise treat as env var name.
    pat_or_env_var = os.environ.get("ADO_PAT_ENV_VAR", "ADO_PAT")
    pat = (
        pat_or_env_var
        if len(pat_or_env_var) >= 40
        else os.environ.get(pat_or_env_var)
    )

    if not org_url:
        raise RuntimeError("ADO_ORG_URL environment variable is required")
    if not project:
        raise RuntimeError("ADO_PROJECT environment variable is required")
    if not pat:
        raise RuntimeError(
            f"PAT not found. Set the {pat_or_env_var} environment variable "
            "with your Azure DevOps Personal Access Token."
        )

    client = AdoClient(org_url, project, pat)
    server = create_server(client)

    print("[ado-mcp-server] Server started successfully", file=sys.stderr)
    server.run(transport="stdio")


if __name__ == "__main__":
    try:
        main()
    except Exception as err:
        print(f"[ado-mcp-server] Fatal error: {err}", file=sys.stderr)
        sys.exit(1)
