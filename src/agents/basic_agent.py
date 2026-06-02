from pydantic import BaseModel
from src.utils.ollama_client import OllamaClient, OllamaConfig
from src.config import settings


class AgentState(BaseModel):
    """Estado do agente."""
    conversation_history: list[dict] = []
    user_id: str = "default"


class BasicAgent:
    def __init__(self, ollama_config: OllamaConfig):
        self.ollama = OllamaClient(ollama_config)
        self.state = AgentState()
        
        # Verificar conexão
        if not self.ollama.health_check():
            raise RuntimeError(f"Ollama não está rodando em {ollama_config.base_url}")
    
    async def process_message(self, user_message: str) -> str:
        """Processa mensagem do usuário."""
        self.state.conversation_history.append({
            "role": "user",
            "content": user_message
        })
        
        # Construir prompt com histórico
        prompt = self._build_prompt(user_message)
        
        # Gerar resposta via Ollama
        response = self.ollama.generate(prompt)
        
        self.state.conversation_history.append({
            "role": "assistant",
            "content": response
        })
        
        return response
    
    def _build_prompt(self, user_message: str) -> str:
        """Constrói prompt com contexto histórico."""
        history_text = "\n".join([
            f"{msg['role']}: {msg['content']}"
            for msg in self.state.conversation_history[-5:]  # Últimas 5 mensagens
        ])
        
        return f"""Você é um assistente pessoal inteligente que ajuda na produtividade e gestão de conhecimento.

Histórico da conversa:
{history_text}

Responda de forma concisa e útil."""
