# Engenharia de Especificação: SPEC-003
## Setup do Repositório e Agente Básico com Ollama

**ID da Atividade:** TASK-003  
**Data de Criação:** 02 de Junho de 2026  
**Data de Conclusão:** 02 de Junho de 2026  
**Status:** ✅ Concluído  
**Autor:** Desenvolvedor Capstone  

---

### 1. Visão Geral
Configurar a base do repositório Git, instalar dependências mínimas (Pydantic AI + Ollama) e implementar um agente básico de teste para validar a integração local entre Pydantic AI e o modelo Ollama rodando na máquina.

---

### 2. Estrutura do Repositório Git

#### 2.1 Layout de Diretórios (Simplificado)
```
ai_upskilling/
├── README.md                          (documentação principal)
├── requirements.txt                   (dependências Python)
├── .env.example                       (template de variáveis)
├── .gitignore                         (Python + dados sensíveis)
│
├── src/
│   ├── __init__.py
│   ├── config.py                      (configurações centralizadas)
│   ├── agents/                        (agentes Pydantic AI)
│   │   ├── __init__.py
│   │   └── basic_agent.py             (Agente de teste com Ollama)
│   ├── utils/
│   │   ├── __init__.py
│   │   └── ollama_client.py           (wrapper para Ollama)
│   └── main.py                        (entrada CLI)
│
├── data/
│   ├── diario/                        (dados pessoais - não versionado)
│   ├── cursos/
│   └── referencias/
│
├── tests/
│   ├── __init__.py
│   └── test_basic_agent.py            (teste do agente)
│
├── docs/
│   ├── SETUP.md                       (guia de configuração)
│   ├── OLLAMA_SETUP.md                (guia de Ollama)
│   └── TROUBLESHOOTING.md             (resolução de problemas)
│
└── scripts/
    ├── setup_venv.sh                  (criar ambiente virtual)
    ├── start_ollama.sh                (iniciar Ollama com cleanup)
    └── kill_ollama.sh                 (finalizar Ollama)
```

---

### 3. Dependências Python (requirements.txt)

**Nota de Implementação:** Versões ajustadas para compatibilidade com Python 3.9

```
# Core Framework
pydantic-ai==0.8.1              # (0.9.0 não existe)

# Configuration
python-dotenv>=1.0.0
pydantic-settings>=2.1.0

# Testing
pytest>=7.4.0
pytest-asyncio>=0.21.0

# CLI
typer>=0.9.0

# Utilities
colorama>=0.4.6
rich>=13.7.0
```

**Versões Instaladas (Resolvidas pelo pip):**
- pydantic: 2.13.4 ✅
- pydantic-ai: 0.8.1 ✅
- requests: 2.32.5 ✅
- pytest: 8.4.2 ✅
- typer: 0.23.2 ✅
- rich: 15.0.0 ✅

---

### 4. Configuração Centralizada (.env.example)

```bash
# Modo de Execução
ENV=development

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=tinyllama            # Modelos disponíveis: tinyllama, mistral (instale com: ollama pull)
OLLAMA_TEMPERATURE=0.7
OLLAMA_MAX_TOKENS=2048

# Agent Configuration
AGENT_NAME=SecondBrain-Basic
AGENT_VERSION=0.1.0

# Data Paths
DATA_ROOT=./data
```

---

### 5. Implementação do Agente Básico

#### 5.1 Wrapper para Ollama (src/utils/ollama_client.py)
```python
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
```

#### 5.2 Agente Básico (src/agents/basic_agent.py)
```python
from pydantic_ai import Agent, RunContext
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
            raise RuntimeError("Ollama não está rodando em {ollama_config.base_url}")
    
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
```

#### 5.3 Configuração (src/config.py)
```python
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
```

#### 5.4 Main CLI (src/main.py)
```python
import asyncio
import typer
from rich.console import Console
from src.agents.basic_agent import BasicAgent
from src.utils.ollama_client import OllamaConfig
from src.config import settings

app = typer.Typer()
console = Console()

@app.command()
def chat():
    """Chat interativo com o agente."""
    ollama_config = OllamaConfig(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        temperature=settings.ollama_temperature,
        max_tokens=settings.ollama_max_tokens
    )
    
    try:
        agent = BasicAgent(ollama_config)
        console.print("[green]✓ Agente conectado ao Ollama[/green]")
    except Exception as e:
        console.print(f"[red]✗ Erro ao conectar: {str(e)}[/red]")
        raise
    
    console.print("\n[cyan]Chat com Second Brain[/cyan]")
    console.print("Digite 'sair' para encerrar\n")
    
    while True:
        try:
            user_input = console.input("[bold]Você:[/bold] ")
            
            if user_input.lower() in ["sair", "exit"]:
                console.print("[yellow]Até logo![/yellow]")
                break
            
            if not user_input.strip():
                continue
            
            console.print("[dim]Pensando...[/dim]")
            response = asyncio.run(agent.process_message(user_input))
            console.print(f"[cyan]Agente:[/cyan] {response}\n")
            
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrompido.[/yellow]")
            break

@app.command()
def test_ollama():
    """Testa conexão com Ollama."""
    config = OllamaConfig(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model
    )
    client = OllamaClient(config)
    
    if client.health_check():
        console.print("[green]✓ Ollama está rodando[/green]")
        # Test simple generation
        response = client.generate("Responda em uma palavra: Como você está?")
        console.print(f"[cyan]Resposta de teste:[/cyan] {response}")
    else:
        console.print("[red]✗ Ollama não está acessível[/red]")

if __name__ == "__main__":
    app()
```

### 6. Setup do Ambiente

#### 6.1 Script de Configuração (scripts/setup_venv.sh)
```bash
#!/bin/bash

echo "🚀 Configurando ambiente virtual..."

# Criar venv
python3 -m venv venv
source venv/bin/activate

# Instalar dependências
pip install --upgrade pip
pip install -r requirements.txt

echo "✓ Ambiente virtual criado"
echo ""
echo "Próximas instruções:"
echo "1. Copiar .env.example para .env e ajustar variáveis"
echo "2. Garantir que Ollama está rodando: ollama serve"
echo "3. Testar agente: python -m src.main test-ollama"
echo "4. Iniciar chat: python -m src.main chat"
```

#### 6.2 Guia de Ollama (docs/OLLAMA_SETUP.md)
```markdown
# Setup do Ollama

## Instalação

\`\`\`bash
# macOS (via Homebrew)
brew install ollama

# ou baixe de https://ollama.ai
\`\`\`

## Iniciar Ollama

\`\`\`bash
ollama serve
\`\`\`

## Baixar Modelo

Em outro terminal:
\`\`\`bash
# Mistral (7B - recomendado para rápido)
ollama pull mistral

# ou Llama 2
ollama pull llama2
\`\`\`

## Testar

\`\`\`bash
curl http://localhost:11434/api/generate -d '{
  "model": "mistral",
  "prompt": "Olá"
}'
\`\`\`
```

#### 6.3 Guia de Setup (docs/SETUP.md)
```markdown
# Setup do Projeto

## Pré-requisitos

- Python 3.9+
- Ollama instalado e rodando
- Git

## Passos

1. Clone o repositório
2. Execute \`bash scripts/setup_venv.sh\`
3. Ative venv: \`source venv/bin/activate\`
4. Copie \`.env.example\` para \`.env\`
5. Confirme que Ollama está rodando: \`ollama serve\` em outro terminal
6. Teste: \`python -m src.main test-ollama\`
7. Inicie o chat: \`python -m src.main chat\`
```

---

### 7. Testes Básicos (tests/test_basic_agent.py)

```python
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
```

---

### 8. Checklist de Implementação

- [x] Criar estrutura de diretórios
- [x] Criar `requirements.txt` com dependências mínimas
- [x] Corrigir versões para Python 3.9
- [x] Criar `.env.example` com configurações
- [x] Implementar `src/config.py`
- [x] Implementar `src/utils/ollama_client.py`
- [x] Implementar `src/agents/basic_agent.py`
- [x] Implementar `src/main.py` com CLI
- [x] Criar `scripts/setup_venv.sh`
- [x] Criar `scripts/start_ollama.sh` (cleanup automático)
- [x] Criar `scripts/kill_ollama.sh` (finalizar processo)
- [x] Criar documentação (SETUP.md, OLLAMA_SETUP.md, TROUBLESHOOTING.md)
- [x] Implementar testes básicos
- [x] Testar conexão com Ollama ✅
- [x] Testar agente em modo interativo ✅
- [x] Documentar resolução de problemas

---

### 9. Estimativa de Esforço

| Tarefa | Estimado | Real |
|:-------|:--------:|:----:|
| Setup repositório | 30 min | 20 min ✅ |
| Código Python | 1-1.5h | 1h ✅ |
| Correção de dependências | - | 30 min |
| Testes | 30 min | 15 min ✅ |
| Documentação | 30 min | 45 min |
| Scripts adicionais | - | 20 min |
| **Total** | **2.5-3h** | **~3.5h** |

---

### 10. Resultado Final ✅

✅ Repositório Git estruturado e pronto  
✅ Ambiente virtual funcionando (Python 3.9.6)  
✅ Agente básico rodando com Ollama localmente  
✅ CLI interativa para testar agente  
✅ Testes básicos implementados  
✅ Agente testado com sucesso (modelo: tinyllama)  
✅ Documentação completa (SETUP, OLLAMA_SETUP, TROUBLESHOOTING)  
✅ Scripts auxiliares criados (start_ollama, kill_ollama)  
✅ Dependências corrigidas para Python 3.9  

### 11. Notas de Implementação

#### Desafios Enfrentados
1. **Versões incompatíveis:** pydantic-ai==0.9.0 não existe (máximo: 0.8.1)
2. **Compatibilidade Python:** pydantic==2.6.0 requer Python 3.10+ (sistema usa 3.9.6)
3. **Conflito de dependências:** requests versões conflitantes
4. **Porta ocupada:** Ollama tentava usar porta 11434 já em uso

#### Soluções Implementadas
1. Flexibilizadas versões no requirements.txt
2. Deixado pip resolver automaticamente as dependências
3. Criado script `kill_ollama.sh` para limpar porta
4. Criado script `start_ollama.sh` com cleanup automático
5. Documentado troubleshooting em `docs/TROUBLESHOOTING.md`

#### Validações Executadas
- ✅ Sintaxe Python validada em todos os arquivos
- ✅ Importações testadas com sucesso
- ✅ Conexão Ollama confirmada
- ✅ Agente gerando respostas (modelo tinyllama)
- ✅ CLI interativa funcionando

---

**Próxima Atividade:** TASK-003-1 - Observabilidade e Setup Avançado
