import requests
from pydantic import BaseModel
from typing import Optional


class OllamaConfig(BaseModel):
    base_url: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 2048


class OllamaClient:
    def __init__(self, config: OllamaConfig):
        self.config = config
    
    def generate(self, prompt: str) -> str:
        """Chama o modelo Ollama local."""
        try:
            response = requests.post(
                f"{self.config.base_url}/api/generate",
                json={
                    "model": self.config.model,
                    "prompt": prompt,
                    "temperature": self.config.temperature,
                    "stream": False
                },
                timeout=30
            )
            response.raise_for_status()
            return response.json()["response"]
        except Exception as e:
            raise RuntimeError(f"Ollama error: {str(e)}")
    
    def health_check(self) -> bool:
        """Verifica se Ollama está rodando."""
        try:
            response = requests.get(f"{self.config.base_url}/api/tags", timeout=5)
            return response.status_code == 200
        except:
            return False
