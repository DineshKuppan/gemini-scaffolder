import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger("mcp_client")


class MCPClient:
    def __init__(self, base_url: str, timeout: int = 10):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    async def call_tool(self, path: str, payload: Dict[str, Any], retries: int = 2) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        backoff = 0.5
        for attempt in range(retries + 1):
            try:
                resp = await self._client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                logger.warning(f"MCP call attempt {attempt} to {url} failed: {e}")
                if attempt == retries:
                    raise
                await asyncio.sleep(backoff * (2 ** attempt))

    async def close(self):
        await self._client.aclose()


def build_client_from_env(env: Optional[Dict[str, str]] = None) -> MCPClient:
    base = None
    if env and env.get("USER_SERVICE_URL"):
        base = env.get("USER_SERVICE_URL")
    else:
        base = "http://user-service:8000"
    return MCPClient(base_url=base)
