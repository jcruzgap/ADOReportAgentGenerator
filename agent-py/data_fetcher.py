import os
import json
from dataclasses import dataclass, field
from typing import Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from .config_loader import ReportConfig


@dataclass
class TaskInfo:
    id: int
    title: str
    state: str
    assigned_to: Optional[str]
    remaining_work: Optional[float]


@dataclass
class WorkItemData:
    id: int
    title: str
    state: str
    tags: list[str]
    assigned_to: Optional[str]
    tasks: list[TaskInfo]


async def fetch_all_data(config: ReportConfig) -> list[WorkItemData]:
    import sys

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp-server-py"],
        env={
            **os.environ,
            "ADO_ORG_URL": config.ado_organization,
            "ADO_PROJECT": config.ado_project,
            "ADO_PAT_ENV_VAR": config.ado_pat_env_var,
        },
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            # 1. Execute WIQL to get work item IDs
            print("  Executing WIQL query...")
            wiql_result = await session.call_tool(
                "ado_execute_wiql", {"query": config.wiql}
            )
            work_item_ids = json.loads(wiql_result.content[0].text)
            print(f"  Found {len(work_item_ids)} work items")

            if not work_item_ids:
                return []

            # 2. Batch-fetch all work items
            ids = [w["id"] for w in work_item_ids]
            print("  Batch-fetching work item details...")
            batch_result = await session.call_tool(
                "ado_get_work_items_batch", {"ids": ids}
            )
            raw_items = json.loads(batch_result.content[0].text)

            # 3. For each work item, fetch child tasks
            print("  Fetching child tasks for each work item...")
            all_data: list[WorkItemData] = []

            for item in raw_items:
                tasks_result = await session.call_tool(
                    "ado_get_work_item_tasks", {"parentId": item["id"]}
                )
                raw_tasks = json.loads(tasks_result.content[0].text)

                tags_str = item["fields"].get("System.Tags", "") or ""
                tags = [t.strip() for t in tags_str.split(";") if t.strip()]

                assigned_to_field = item["fields"].get("System.AssignedTo")
                assigned_to = (
                    assigned_to_field.get("displayName")
                    if isinstance(assigned_to_field, dict)
                    else None
                )

                tasks = []
                for t in raw_tasks:
                    t_assigned = t["fields"].get("System.AssignedTo")
                    tasks.append(TaskInfo(
                        id=t["id"],
                        title=t["fields"]["System.Title"],
                        state=t["fields"]["System.State"],
                        assigned_to=(
                            t_assigned.get("displayName")
                            if isinstance(t_assigned, dict)
                            else None
                        ),
                        remaining_work=t["fields"].get(
                            "Microsoft.VSTS.Scheduling.RemainingWork"
                        ),
                    ))

                all_data.append(WorkItemData(
                    id=item["id"],
                    title=item["fields"]["System.Title"],
                    state=item["fields"]["System.State"],
                    tags=tags,
                    assigned_to=assigned_to,
                    tasks=tasks,
                ))

            return all_data
