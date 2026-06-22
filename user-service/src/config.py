from pydantic import BaseSettings


class Settings(BaseSettings):
    SERVICE_NAME: str = "user-service"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DATABASE_DIR: str = "/tmp"
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()
