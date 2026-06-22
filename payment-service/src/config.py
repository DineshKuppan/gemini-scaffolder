from pydantic import BaseSettings


class Settings(BaseSettings):
    SERVICE_NAME: str = "payment-service"
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    DATABASE_URL: str = "sqlite:///./payment.db"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
