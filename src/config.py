from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    env: str = "development"
    
    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    ollama_temperature: float = 0.7
    ollama_max_tokens: int = 2048
    
    # Agent
    agent_name: str = "SecondBrain-Basic"
    agent_version: str = "0.1.0"
    
    # Data
    data_root: str = "./data"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
