import os
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, Callable, Union
from litellm import completion, token_counter
from pydantic import BaseModel, Field

# Configure structured JSON logging
from shared.logging_config import configure_logging
configure_logging("gemini-adk-wrapper")
logger = logging.getLogger("gemini-adk-wrapper")

class LLMResponse(BaseModel):
    """Standardized response object for the LLM proxy."""
    content: str
    model: str
    usage: Dict[str, Any]
    finish_reason: Optional[str] = None

class LiteLLMProxy:
    """
    A production-grade wrapper around LiteLLM providing fallback mechanisms,
    cost tracking, and an output evaluation loop.
    """
    def __init__(
        self,
        primary_model: str = os.getenv("PRIMARY_MODEL", "gemini/gemini-1.5-pro-latest"),
        fallback_models: List[str] = os.getenv("FALLBACK_MODELS", "openai/gpt-4-turbo,anthropic/claude-3-5-sonnet-20240620").split(","),
        max_retries: int = 2
    ):
        self.primary_model = primary_model
        self.fallback_models = fallback_models
        self.max_retries = max_retries
        self.all_models = [self.primary_model] + self.fallback_models

    async def generate_with_evaluation(
        self,
        messages: List[Dict[str, str]],
        validator: Optional[Callable[[str], bool]] = None,
        max_eval_attempts: int = 3,
        **kwargs
    ) -> LLMResponse:
        """
        Executes a completion request with a fallback engine and an evaluation loop.
        If the validator fails, it retries the generation (potentially with a different model).
        """
        last_exception = None
        
        for model in self.all_models:
            eval_attempt = 0
            while eval_attempt < max_eval_attempts:
                try:
                    logger.info(f"Requesting completion from model: {model} (Eval Attempt: {eval_attempt + 1})")
                    
                    # LiteLLM completion call (async)
                    response = await completion(
                        model=model,
                        messages=messages,
                        **kwargs
                    )

                    content = response.choices[0].message.content
                    usage = dict(response.get("usage", {}))
                    finish_reason = response.choices[0].finish_reason

                    # Output Evaluation Loop
                    if validator:
                        if validator(content):
                            logger.info(f"Validation passed for model {model}.")
                            return LLMResponse(
                                content=content,
                                model=model,
                                usage=usage,
                                finish_reason=finish_reason
                            )
                        else:
                            logger.warning(f"Validation failed for model {model} on attempt {eval_attempt + 1}.")
                            eval_attempt += 1
                            # Optional: Append a system message or hint to the messages for the next attempt
                            messages.append({"role": "system", "content": "Your previous output failed validation. Please ensure the output strictly follows the required format/schema."})
                            continue
                    
                    return LLMResponse(
                        content=content,
                        model=model,
                        usage=usage,
                        finish_reason=finish_reason
                    )

                except Exception as e:
                    logger.error(f"Error during completion with model {model}: {str(e)}")
                    last_exception = e
                    # Break inner loop to try next model in fallback list
                    break 
            
        if last_exception:
            raise last_exception
        raise Exception("LLM Proxy failed to return a valid response after exhausting all models and evaluation attempts.")

    @staticmethod
    def json_validator(content: str) -> bool:
        """A standard validator to ensure the LLM output is valid JSON."""
        try:
            # Clean potential markdown code blocks
            cleaned = content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            
            json.loads(cleaned.strip())
            return True
        except (ValueError, json.JSONDecodeError):
            return False

    async def get_token_count(self, text: str, model: Optional[str] = None) -> int:
        """Utility to count tokens for a given string and model."""
        target_model = model or self.primary_model
        try:
            return token_counter(model=target_model, text=text)
        except Exception:
            # Fallback to a rough estimate if model-specific tokenizer fails
            return len(text) // 4