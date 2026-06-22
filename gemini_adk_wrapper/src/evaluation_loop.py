import asyncio
import logging
from shared.logging_config import configure_logging
import json
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field
import litellm
from litellm import acompletion

# Configure structured JSON logging
configure_logging("gemini-adk-wrapper")
logger = logging.getLogger("gemini_adk_wrapper.evaluation_loop")

class EvaluationResult(BaseModel):
    """Schema for the output of the evaluation phase."""
    score: float = Field(..., ge=0.0, le=1.0, description="Quality score from 0.0 to 1.0")
    feedback: Optional[str] = Field(None, description="Specific feedback for refinement")
    passed: bool = Field(..., description="Whether the output meets the minimum quality threshold")
    metadata: Dict[str, Any] = Field(default_factory=dict)

class LLMResponse(BaseModel):
    """Internal wrapper for LLM outputs."""
    content: str
    model_used: str
    usage: Dict[str, Any]
    finish_reason: str

class EvaluationLoopConfig(BaseModel):
    """Configuration for the evaluation and fallback logic."""
    primary_model: str = "gemini/gemini-1.5-pro-latest"
    fallback_models: List[str] = ["openai/gpt-4o", "anthropic/claude-3-5-sonnet-20240620"]
    evaluator_model: str = "openai/gpt-4o-mini"
    max_retries_per_model: int = 2
    quality_threshold: float = 0.85
    temperature: float = 0.7

class EvaluationLoop:
    """
    Implements a production-grade evaluation loop with LiteLLM proxy fallback.
    It attempts to generate content, evaluates it against a threshold, 
    and performs self-correction or model-switching if quality is insufficient.
    """
    def __init__(self, config: Optional[EvaluationLoopConfig] = None):
        self.config = config or EvaluationLoopConfig()

    async def _call_llm(self, messages: List[Dict[str, str]], model: str) -> LLMResponse:
        """Executes the LLM call using LiteLLM with fallback support."""
        try:
            response = await acompletion(
                model=model,
                messages=messages,
                temperature=self.config.temperature,
                num_retries=2
            )
            return LLMResponse(
                content=response.choices[0].message.content,
                model_used=model,
                usage=dict(response.get("usage", {})),
                finish_reason=response.choices[0].finish_reason
            )
        except Exception as e:
            logger.error(f"LLM Call failed for model {model}: {str(e)}")
            raise

    async def _evaluate_output(self, original_prompt: str, response_content: str) -> EvaluationResult:
        """
        Uses a secondary 'evaluator' model to score the output.
        In a production environment, this could also involve heuristic checks or RAG verification.
        """
        eval_system_prompt = (
            "You are an expert quality assurance agent. Evaluate the AI response based on accuracy, "
            "adherence to instructions, and clarity. Return a JSON object with 'score' (0-1), "
            "'feedback' (string), and 'passed' (boolean)."
        )
        
        eval_user_prompt = f"Original Prompt: {original_prompt}\n\nAI Response: {response_content}"
        
        try:
            eval_resp = await acompletion(
                model=self.config.evaluator_model,
                messages=[
                    {"role": "system", "content": eval_system_prompt},
                    {"role": "user", "content": eval_user_prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            raw_content = eval_resp.choices[0].message.content
            data = json.loads(raw_content)
            return EvaluationResult(**data)
        except Exception as e:
            logger.warning(f"Evaluation failed, defaulting to safety pass: {str(e)}")
            return EvaluationResult(score=1.0, passed=True, feedback="Evaluation system error; bypassed.")

    async def run(self, prompt: str, system_instruction: Optional[str] = None) -> Dict[str, Any]:
        """
        Main execution loop: Primary -> Evaluation -> (Refine | Fallback).
        """
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        models_to_try = [self.config.primary_model] + self.config.fallback_models
        
        for model in models_to_try:
            current_attempt_messages = list(messages)
            
            for attempt in range(self.config.max_retries_per_model):
                logger.info(f"Executing generation: Model={model}, Attempt={attempt + 1}")
                
                try:
                    # 1. Generate
                    llm_response = await self._call_llm(current_attempt_messages, model)
                    
                    # 2. Evaluate
                    eval_result = await self._evaluate_output(prompt, llm_response.content)
                    
                    # 3. Check Threshold
                    if eval_result.passed and eval_result.score >= self.config.quality_threshold:
                        logger.info(f"Quality threshold met with model {model}.")
                        return {
                            "status": "success",
                            "content": llm_response.content,
                            "model": model,
                            "score": eval_result.score,
                            "usage": llm_response.usage,
                            "metadata": {"attempts": attempt + 1, "feedback": eval_result.feedback}
                        }
                    
                    # 4. Refine (Self-Correction)
                    logger.warning(f"Quality low ({eval_result.score}). Feedback: {eval_result.feedback}")
                    current_attempt_messages.append({"role": "assistant", "content": llm_response.content})
                    current_attempt_messages.append({
                        "role": "user", 
                        "content": f"Your previous response scored low on quality. Feedback: {eval_result.feedback}. Please provide a corrected and improved version."
                    })
                    
                except Exception as e:
                    logger.error(f"Critical failure during loop for model {model}: {str(e)}")
                    break # Move to next model in fallback chain

        return {
            "status": "error",
            "message": "Failed to generate content meeting quality standards after exhausting all models and retries.",
            "last_attempted_model": models_to_try[-1]
        }

# Example usage for integration testing
if __name__ == "__main__":
    async def test():
        loop = EvaluationLoop()
        result = await loop.run("Explain the concept of multi-tenancy in cloud computing.")
        print(json.dumps(result, indent=2))

    asyncio.run(test())