import json
from mcp.server.fastmcp import FastMCP
from .ado_client import AdoClient


def create_server(client: AdoClient) -> FastMCP:
    mcp = FastMCP("ado-mcp-server")

    @mcp.tool()
    async def ado_execute_wiql(query: str) -> str:
        """Execute a WIQL query and return matching work item IDs."""
        items = await client.execute_wiql(query)
        return json.dumps(items)

    @mcp.tool()
    async def ado_get_work_item(id: int, expand: str = "relations") -> str:
        """Fetch a single work item by ID including its relations."""
        item = await client.get_work_item(id, expand)
        return json.dumps(item)

    @mcp.tool()
    async def ado_get_work_item_tasks(parentId: int) -> str:
        """Fetch all child tasks of a given parent work item."""
        parent = await client.get_work_item(parentId, "relations")
        relations = parent.get("relations") or []
        child_ids = []
        for r in relations:
            if r.get("rel") == "System.LinkTypes.Hierarchy-Forward":
                url: str = r["url"]
                child_ids.append(int(url[url.rfind("/") + 1 :]))

        if not child_ids:
            return "[]"

        tasks = await client.get_work_items_batch(child_ids)
        return json.dumps(tasks)

    @mcp.tool()
    async def ado_get_work_items_batch(
        ids: list[int], fields: list[str] | None = None
    ) -> str:
        """Fetch multiple work items by their IDs in a single batch call."""
        items = await client.get_work_items_batch(ids, fields)
        return json.dumps(items)

    return mcp
