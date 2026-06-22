import os
import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from mcp_client import MCPClient
from evaluation_loop import EvaluationLoop, EvaluationLoopConfig
import asyncio

logger = logging.getLogger("gemini.adk.chat")

router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class CompletionRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000
    tenant_id: Optional[str] = Field(None, description="Tenant identifier for multi-tenant tracking")
    user_id: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    evaluation_criteria: Optional[str] = None


class ProxyResponse(BaseModel):
    id: str
    choices: List[Dict[str, Any]]
    model: str
    usage: Dict[str, Any]


@router.post("/v1/chat/completions", response_model=ProxyResponse)
async def chat_completion(request: CompletionRequest, x_tenant_id: Optional[str] = Header(None)):
    tenant = x_tenant_id or request.tenant_id
    if not tenant:
        raise HTTPException(status_code=400, detail="tenant_id or X-Tenant-ID header required")

    # Build MCP clients
    user_base = os.getenv("USER_SERVICE_URL", "http://user-service:8000")
    payment_base = os.getenv("PAYMENT_SERVICE_URL", "http://payment-service:8001")
    user_client = MCPClient(base_url=user_base)
    payment_client = MCPClient(base_url=payment_base)

    # Fetch contexts
    context_parts = []
    try:
        if request.user_id:
            try:
                uresp = await user_client.call_tool("/mcp/tools/get_user_context", {"tenant_id": tenant, "user_id": request.user_id})
                context_parts.append(uresp.get("result") if isinstance(uresp, dict) else str(uresp))
            except Exception as e:
                logger.warning(f"User MCP call failed: {e}")

            try:
                presp = await payment_client.call_tool("/mcp/tools/get_balance_context", {"tenant_id": tenant, "user_id": request.user_id, "start_date": request.start_date, "end_date": request.end_date})
                context_parts.append(presp.get("result") if isinstance(presp, dict) else str(presp))
            except Exception as e:
                logger.warning(f"Payment MCP call failed: {e}")

        # Inject contexts as a system message
        system_msg = {"role": "system", "content": "\n\n".join(context_parts) if context_parts else ""}
        messages = [m.dict() for m in request.messages]
        if system_msg["content"]:
            messages.insert(0, system_msg)

        model_name = request.model or os.getenv("PRIMARY_MODEL", "gemini/gemini-1.5-pro-latest")

        # Build a text prompt from messages for the EvaluationLoop
        prompt_parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            prompt_parts.append(f"[{role}] {content}")
        prompt_text = "\n\n".join(prompt_parts)

        eval_config = EvaluationLoopConfig(primary_model=model_name)
        loop_runner = EvaluationLoop(config=eval_config)

        result = await loop_runner.run(prompt=prompt_text, system_instruction=system_msg.get("content", None))

        if result.get("status") != "success":
            raise HTTPException(status_code=500, detail=result.get("message", "Generation failed"))

        return ProxyResponse(id=result.get("model", ""), choices=[{"message": {"role": "assistant", "content": result.get("content")}}], model=result.get("model"), usage=result.get("usage", {}))
    finally:
        await user_client.close()
        await payment_client.close()
