from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Configuration settings for the Gemini ADK Wrapper service.
    Handles environment variables for Gemini API, LiteLLM proxy fallbacks,
    and evaluation loop parameters.
    """
    # Application Metadata
    APP_NAME: str = "gemini-adk-wrapper"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # API Security
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "super-secret-key-for-internal-auth"
    
    # Gemini Configuration
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Primary Google Gemini API Key")
    GEMINI_MODEL_NAME: str = Field(default="gemini-1.5-pro-latest", description="Default Gemini model to use")

    # LiteLLM Proxy Configuration (Fallback Engine)
    # This allows the service to route to OpenAI, Anthropic, etc., if Gemini fails
    LITELLM_PROXY_URL: Optional[str] = Field(default=None, description="URL for the LiteLLM Proxy server")
    LITELLM_API_KEY: Optional[str] = Field(default=None, description="API Key for the LiteLLM Proxy")
    
    # Fallback Strategy
    ENABLE_FALLBACK: bool = Field(default=True, description="Whether to attempt fallback models on failure")
    FALLBACK_MODELS: List[str] = Field(
        default=["gpt-4o", "claude-3-5-sonnet-20240620"],
        description="Ordered list of models to try if the primary model fails"
    )

    # Evaluation Loop Settings
    # Used to verify the quality of the LLM output before returning to the client
    MAX_EVALUATION_RETRIES: int = Field(default=3, description="Max attempts to refine output via evaluation loop")
    EVALUATION_THRESHOLD: float = Field(default=0.8, description="Minimum score required from the evaluator (0.0 to 1.0)")
    EVALUATOR_MODEL: str = Field(default="gpt-4o", description="Model used to evaluate the primary output")

    # Infrastructure
    CORS_ORIGINS: List[str] = ["*"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

settings = Settings()