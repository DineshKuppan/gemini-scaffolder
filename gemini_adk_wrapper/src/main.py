import os
import logging
from shared.logging_config import configure_logging
import json
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel, Field
from litellm import completion, embedding
from mcp.server.fastmcp import FastMCP
from api.chat import router as chat_router

# Configure structured JSON logging
configure_logging("gemini-adk-wrapper")
logger = logging.getLogger("gemini-adk-wrapper")

# Initialize FastAPI app
app = FastAPI(title="Gemini ADK Wrapper", version="1.0.0")

# Initialize FastMCP for tool discovery
mcp = FastMCP("GeminiADK")

try:
    import importlib.util
    svc_dir = os.path.dirname(__file__)
    tenant_path = os.path.join(svc_dir, "middleware", "tenant.py")
    if os.path.exists(tenant_path):
        spec = importlib.util.spec_from_file_location("service_tenant_middleware", tenant_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        TenantMiddleware = getattr(module, "TenantMiddleware")
        if TenantMiddleware:
            app.add_middleware(TenantMiddleware)
except Exception:
    pass

try:
    import importlib.util
    svc_dir = os.path.dirname(__file__)
    logging_path = os.path.join(svc_dir, "middleware", "logging.py")
    if os.path.exists(logging_path):
        spec = importlib.util.spec_from_file_location("service_logging_middleware", logging_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        LoggingMiddleware = getattr(module, "LoggingMiddleware")
        if LoggingMiddleware:
            app.add_middleware(LoggingMiddleware)
except Exception:
    pass

# Configuration
PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gemini/gemini-1.5-pro-latest")
FALLBACK_MODELS = os.getenv("FALLBACK_MODELS", "gpt-4-turbo,claude-3-opus-20240229").split(",")
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "3"))

class ChatMessage(BaseModel):
    role: str
    content: str

class CompletionRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 1000
    tenant_id: str = Field(..., description="Tenant identifier for multi-tenant tracking")
    evaluation_criteria: Optional[str] = Field(None, description="Optional criteria to evaluate the output against")

class EvaluationResult(BaseModel):
    passed: bool
    reason: Optional[str] = None
    refined_prompt: Optional[str] = None

class ProxyResponse(BaseModel):
    id: str
    choices: List[Dict[str, Any]]
    model: str
    usage: Dict[str, Any]
    evaluation: Optional[EvaluationResult] = None

async def evaluate_output(content: str, criteria: str) -> EvaluationResult:
    """
    Internal evaluation loop to check if the LLM output meets specific criteria.
    In a production scenario, this could call another LLM or a deterministic validator.
    """
    try:
        # Simple heuristic: if criteria is 'json', check if content is parseable
        if criteria.lower() == "json":
            try:
                json.loads(content)
                return EvaluationResult(passed=True)
            except ValueError:
                return EvaluationResult(
                    passed=False, 
                    reason="Output is not valid JSON",
                    refined_prompt="The previous output was not valid JSON. Please ensure the response is strictly valid JSON."
                )
        
        # Default pass if no specific logic implemented for criteria
        return EvaluationResult(passed=True)
    except Exception as e:
        logger.error(f"Evaluation error: {str(e)}")
        return EvaluationResult(passed=False, reason=f"Evaluation system error: {str(e)}")

@app.post("/v1/chat/completions", response_model=ProxyResponse)
async def chat_completion(
    request: CompletionRequest,
    x_tenant_id: str = Header(None)
):
    tenant_id = x_tenant_id or request.tenant_id
    model_list = [request.model or PRIMARY_MODEL] + FALLBACK_MODELS
    
    last_exception = None
    
    for model_name in model_list:
        try:
            logger.info(f"Attempting completion with model: {model_name} for tenant: {tenant_id}")
            
            # LiteLLM Proxy Call
            response = completion(
                model=model_name,
                messages=[m.dict() for m in request.messages],
                temperature=request.temperature,
                max_tokens=request.max_tokens
            )
            
            content = response.choices[0].message.content
            
            # Evaluation Loop
            if request.evaluation_criteria:
                eval_res = await evaluate_output(content, request.evaluation_criteria)
                if not eval_res.passed and eval_res.refined_prompt:
                    logger.warning(f"Evaluation failed for {model_name}: {eval_res.reason}. Retrying with refinement.")
                    # Single retry with refined prompt
                    refined_messages = [m.dict() for m in request.messages] + [
                        {"role": "assistant", "content": content},
                        {"role": "user", "content": eval_res.refined_prompt}
                    ]
                    response = completion(
                        model=model_name,
                        messages=refined_messages,
                        temperature=request.temperature
                    )
                    content = response.choices[0].message.content
                    # Re-evaluate
                    eval_res = await evaluate_output(content, request.evaluation_criteria)
                
                return ProxyResponse(
                    id=response.id,
                    choices=[{"message": {"role": "assistant", "content": content}}],
                    model=model_name,
                    usage=dict(response.usage),
                    evaluation=eval_res
                )

            return ProxyResponse(
                id=response.id,
                choices=[{"message": {"role": "assistant", "content": content}}],
                model=model_name,
                usage=dict(response.usage)
            )

        except Exception as e:
            logger.error(f"Model {model_name} failed: {str(e)}")
            last_exception = e
            continue

    raise HTTPException(status_code=500, detail=f"All models failed. Last error: {str(last_exception)}")

@mcp.tool()
async def evaluate_llm_response(text: str, schema_type: str) -> str:
    """
    MCP Tool to evaluate if a response matches a specific schema (e.g., 'json').
    """
    result = await evaluate_output(text, schema_type)
    return json.dumps(result.dict())

@app.get("/health")
async def health_check():
    return {"status": "healthy", "primary_model": PRIMARY_MODEL}


# Include chat router that enriches prompts using MCP
try:
    app.include_router(chat_router)
except Exception:
    # best-effort include (when module path resolution differs in some runtimes)
    pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)