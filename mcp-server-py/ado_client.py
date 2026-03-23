import asyncio
import base64
import math
from typing import Any, Optional
import httpx


def _chunk_list(lst: list, size: int) -> list[list]:
    return [lst[i : i + size] for i in range(0, len(lst), size)]


async def _with_retry(
    fn,
    max_retries: int = 3,
    base_delay: float = 1.0,
):
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except httpx.HTTPStatusError as err:
            last_error = err
            status = err.response.status_code
            if attempt < max_retries and (status == 429 or 500 <= status < 600):
                delay = base_delay * math.pow(2, attempt)
                print(
                    f"[ado-client] Retrying in {delay:.0f}s "
                    f"(attempt {attempt + 1}/{max_retries})..."
                )
                await asyncio.sleep(delay)
                continue
            raise
        except Exception as err:
            last_error = err
            raise
    raise last_error


class AdoClient:
    def __init__(self, org_url: str, project: str, pat: str):
        token = base64.b64encode(f":{pat}".encode()).decode()
        self._api_base = f"{org_url.rstrip('/')}/{project}/_apis"
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _url(self, path: str) -> str:
        return f"{self._api_base}/{path}?api-version=7.1"

    async def close(self):
        await self._client.aclose()

    async def execute_wiql(self, query: str) -> list[dict]:
        async def _call():
            resp = await self._client.post(
                self._url("wit/wiql"), json={"query": query}
            )
            resp.raise_for_status()
            return resp.json().get("workItems", [])

        return await _with_retry(_call)

    async def get_work_item(
        self, item_id: int, expand: Optional[str] = None
    ) -> dict:
        async def _call():
            url = f"{self._api_base}/wit/workitems/{item_id}?api-version=7.1&$expand={expand or 'relations'}"
            resp = await self._client.get(url)
            resp.raise_for_status()
            return resp.json()

        return await _with_retry(_call)

    async def get_work_items_batch(
        self, ids: list[int], fields: Optional[list[str]] = None
    ) -> list[dict]:
        if not ids:
            return []

        chunks = _chunk_list(ids, 200)
        results: list[dict] = []

        for chunk in chunks:
            body: dict[str, Any] = {"ids": chunk}
            if fields:
                body["fields"] = fields
            else:
                body["$expand"] = "relations"

            async def _call(b=body):
                resp = await self._client.post(
                    self._url("wit/workitemsbatch"), json=b
                )
                resp.raise_for_status()
                return resp.json().get("value", [])

            data = await _with_retry(_call)
            results.extend(data)

        return results
