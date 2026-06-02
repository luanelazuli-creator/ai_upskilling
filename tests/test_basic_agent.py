import pytest
from src.agents.basic_agent import BasicAgent, AgentState
from src.utils.ollama_client import OllamaClient, OllamaConfig
from src.config import settings


@pytest.fixture
def ollama_config():
    return OllamaConfig(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model
    )


def test_ollama_health(ollama_config):
    """Testa conexão com Ollama."""
    client = OllamaClient(ollama_config)
    assert client.health_check(), "Ollama não está rodando"


@pytest.mark.asyncio
async def test_agent_message(ollama_config):
    """Testa processamento básico de mensagem."""
    agent = BasicAgent(ollama_config)
    response = await agent.process_message("Qual é o seu nome?")
    assert response is not None
    assert len(response) > 0


def test_agent_state():
    """Testa estado do agente."""
    state = AgentState(user_id="test_user")
    assert state.conversation_history == []
    assert state.user_id == "test_user"
