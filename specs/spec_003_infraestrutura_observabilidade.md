# Engenharia de Especificação: SPEC-003
## Infraestrutura Base e Observabilidade (OTel)

**ID da Atividade:** TASK-003  
**Data de Criação:** 02 de Junho de 2026  
**Status:** Planejado (Implementação em Andamento)  
**Autor:** Desenvolvedor Capstone  

---

### 1. Visão Geral
Estabelecer a base de infraestrutura do projeto, configurar as dependências principais (Pydantic AI, OpenTelemetry) e implementar observabilidade local para auditoria de chamadas de agentes e traces de execução sem transmissão de dados para serviços externos.

---

### 2. Estrutura do Repositório Git

#### 2.1 Layout de Diretórios
```
ai_upskilling/
├── README.md                          (documentação principal do projeto)
├── requirements.txt                   (dependências Python)
├── .env.example                       (template de variáveis de ambiente)
├── .gitignore                         (padrão Python + dados sensíveis)
│
├── src/
│   ├── __init__.py
│   ├── config.py                      (configurações centralizadas)
│   ├── logging_config.py              (setup de OpenTelemetry)
│   ├── agents/                        (agentes Pydantic AI)
│   │   ├── __init__.py
│   │   ├── agent1_router.py           (Agente 1: Triagem e Contexto)
│   │   ├── agent2_synthesis.py        (Agente 2: Síntese e RAG)
│   │   └── agent3_memory.py           (Agente 3: Memória e Guardrails)
│   ├── rag/                           (módulo de RAG local)
│   │   ├── __init__.py
│   │   ├── vectorizer.py              (vetorização de documentos)
│   │   ├── retriever.py               (busca semântica local)
│   │   └── store.py                   (gerenciador de índices locais)
│   ├── memory/                        (persistência de memória)
│   │   ├── __init__.py
│   │   ├── episodic.py                (memória episódica)
│   │   ├── semantic.py                (memória semântica)
│   │   └── guardrails.py              (sanitização de PII)
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── converters.py              (conversão de formatos: docx → md)
│   │   └── validators.py              (validações gerais)
│   └── main.py                        (entrada CLI do sistema)
│
├── data/
│   ├── diario/
│   │   └── 2026/06/
│   │       ├── 2026-06-11_keep_studying.md
│   │       └── 2026-06-12_studying_mcp.md
│   ├── cursos/
│   │   ├── Golden Prompts/
│   │   │   └── prompt_pesquisa_academica.md
│   │   └── cursos_feitos.md
│   └── referencias/
│       ├── acessos_sistemas.md
│       ├── atestados.md
│       ├── glossario.md
│       ├── links_uteis.md
│       ├── pessoas_importantes.md
│       └── contatos_thoughtworks.md
│
├── evals/                             (Pydantic Evals - TASK-009)
│   ├── __init__.py
│   ├── dataset.json                   (casos de teste)
│   ├── metrics.py                     (métricas customizadas)
│   └── evaluation_suite.py            (orquestração de testes)
│
├── observability/                     (OpenTelemetry local)
│   ├── __init__.py
│   ├── tracer.py                      (configuração de traces)
│   ├── exporters.py                   (exportadores locais)
│   └── dashboards/
│       └── traces.json                (exports de traces em JSON)
│
├── tests/
│   ├── __init__.py
│   ├── test_agents.py
│   ├── test_rag.py
│   └── test_memory.py
│
├── docs/
│   ├── ARCHITECTURE.md                (diagrama de arquitetura)
│   ├── AGENTS.md                      (especificação de cada agente)
│   └── SETUP.md                       (guia de configuração)
│
└── scripts/
    ├── setup_venv.sh                  (configurar ambiente virtual)
    ├── convert_data.py                (converter dados para .md)
    └── run_evals.py                   (executar suite de avaliações)
```

---

### 3. Dependências Python (requirements.txt)

```
# Core Framework
pydantic==2.6.0
pydantic-ai==0.x.x          # Will be determined at install time

# OpenTelemetry Stack
opentelemetry-api==1.21.0
opentelemetry-sdk==1.21.0
opentelemetry-exporter-jaeger-thrift==1.21.0
opentelemetry-exporter-otlp==0.42b0
opentelemetry-instrumentation==0.42b0

# Local Vector Store & RAG
chromadb==0.4.x             # Vector database local
sentence-transformers==2.2.x # Embedding model (BERT-based)

# Data Processing
pandas==2.1.x
openpyxl==3.10.x            # Excel parsing
python-docx==0.8.x          # DOCX parsing
pandoc==2.3                  # Format conversion (docx → md)

# Memory & Persistence
sqlalchemy==2.0.x           # ORM para banco local
pydantic-settings==2.x      # Configurações baseadas em Pydantic

# Evaluation Framework
pytest==7.4.x
pytest-cov==4.1.x

# Logging & Monitoring
python-dotenv==1.0.x        # Carregamento de .env

# LLM API Integration
anthropic==0.x.x            # AWS Bedrock / Claude (se aplicável)
openai==1.x.x               # OpenAI (fallback ou benchmark)
```

---

### 4. Configuração Centralizada (config.py)

**Variáveis de Ambiente (.env):**
```bash
# Mode
ENV=development  # development | production

# OpenTelemetry
OTEL_EXPORTER=jaeger              # jaeger | otlp | console
OTEL_SERVICE_NAME=secondbrain
OTEL_JAEGER_AGENT_HOST=localhost
OTEL_JAEGER_AGENT_PORT=6831

# RAG & Vector Store
VECTOR_STORE_PATH=./data/.vectorstore
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
CHUNK_SIZE=1000
CHUNK_OVERLAP=200

# Memory Storage
MEMORY_DB_PATH=./data/.memory.db
GUARDRAIL_ENABLED=true
PII_DETECTION_MODEL=roberta-pii-detection  # ou equivalente

# LLM Configuration
LLM_PROVIDER=bedrock              # bedrock | openai
LLM_MODEL_ID=claude-3-haiku       # Anthropic Haiku (low cost)
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=2048

# Data Paths
DATA_ROOT=./data
DIARIO_PATH=./data/diario
CURSOS_PATH=./data/cursos
REFERENCIAS_PATH=./data/referencias

# Evaluation
EVAL_ENABLED=true
EVAL_BASELINE_ENABLED=true        # Rodar benchmark single-agent
```

---

### 5. Setup do OpenTelemetry (Observabilidade Local)

#### 5.1 Exportação Local (Console + JSON Dumps)
```python
# observability/tracer.py
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
import json
import os

def init_tracer(service_name: str):
    """Inicializa o tracer com exportadores locais."""
    
    resource = Resource.create({SERVICE_NAME: service_name})
    tracer_provider = TracerProvider(resource=resource)
    
    # Exportador 1: Jaeger local (interface web opcional)
    jaeger_exporter = JaegerExporter(
        agent_host_name="localhost",
        agent_port=6831,
    )
    tracer_provider.add_span_processor(SimpleSpanProcessor(jaeger_exporter))
    
    # Exportador 2: Dumper JSON local (sem rede)
    trace.set_tracer_provider(tracer_provider)
    return tracer_provider

def log_trace_to_json(span_data, output_dir="./observability/dashboards"):
    """Exporta trace para JSON local para auditoria."""
    os.makedirs(output_dir, exist_ok=True)
    trace_dict = {
        "trace_id": str(span_data.trace_id),
        "span_id": str(span_data.span_id),
        "name": span_data.name,
        "start_time": span_data.start_time,
        "end_time": span_data.end_time,
        "attributes": dict(span_data.attributes),
        "events": [{"name": e.name, "attributes": dict(e.attributes)} for e in span_data.events]
    }
    
    filename = f"{output_dir}/trace_{span_data.trace_id}.json"
    with open(filename, 'w') as f:
        json.dump(trace_dict, f, indent=2)
```

#### 5.2 Instrumentação de Agentes
```python
# Cada agente será instrumentado para rastrear:
# - Entrada (usuário prompt)
# - Roteamento (qual agente foi escolhido)
# - Busca RAG (documentos recuperados)
# - Saída (resposta gerada)
# - Latência total
```

---

### 6. Stack de Pydantic AI

#### 6.1 Estrutura Base de Agentes
```python
# src/agents/__init__.py
from pydantic_ai import Agent, RunContext
from pydantic_ai.tools import Tool
from pydantic import BaseModel

class AgentState(BaseModel):
    """Estado compartilhado entre agentes."""
    user_id: str
    conversation_history: list[dict]
    context: dict  # metadados de roteamento

# Cada agente será uma instância de pydantic_ai.Agent
# com tools customizados para:
# - Agent 1: análise de intenção, busca temporal
# - Agent 2: busca semântica RAG, síntese
# - Agent 3: gerenciamento de memória, sanitização PII
```

#### 6.2 Integração com LLM
```python
# Pydantic AI suporta múltiplos LLM providers
# - Claude (Anthropic/Bedrock)
# - GPT (OpenAI)
# - Ollama (local, sem API)
```

---

### 7. Checklist de Implementação

**Fase A: Infraestrutura Base**
- [ ] Criar estrutura de diretórios Git
- [ ] Inicializar `requirements.txt` com dependências core
- [ ] Criar `.env.example` e arquivo `config.py` centralizado
- [ ] Setup de ambiente virtual (venv)
- [ ] Documentação `SETUP.md` com instruções de clone/build

**Fase B: OpenTelemetry**
- [ ] Implementar `observability/tracer.py`
- [ ] Criar exportadores locais (Jaeger + JSON)
- [ ] Testar coleta de traces básicos
- [ ] Documentar dashboard de traces

**Fase C: Pydantic AI Setup**
- [ ] Instalar Pydantic AI
- [ ] Criar estrutura base de `src/agents/`
- [ ] Implementar context/state compartilhado
- [ ] Configurar integração com LLM (Claude via Bedrock ou OpenAI)

**Fase D: Conversão de Dados**
- [ ] Script `scripts/convert_data.py` para migrar .docx/.xlsx → .md
- [ ] Rodar conversão nos dados existentes
- [ ] Validar estrutura pós-conversão

**Fase E: Teste Básico (Smoke Test)**
- [ ] Criar `tests/test_infrastructure.py`
- [ ] Verificar load de configurações
- [ ] Validar tracing end-to-end
- [ ] Confirmar conectividade com LLM

---

### 8. Estimativa de Esforço

| Fase | Duração Estimada | Bloqueadores |
|:-----|:---------------:|:-------------|
| A - Infraestrutura | 1-2 horas | Nenhum |
| B - OpenTelemetry | 2-3 horas | Instalação de Jaeger (opcional) |
| C - Pydantic AI | 2-3 horas | Chave de API (Claude/OpenAI) |
| D - Conversão Dados | 1-2 horas | Qualidade do Pandoc |
| E - Smoke Tests | 1-2 horas | Nenhum |
| **Total** | **7-12 horas** | **Chave API e internet** |

---

### 9. Resultado Esperado

Ao final da TASK-003, teremos:

✅ Repositório Git estruturado e documentado  
✅ Todas as dependências instaladas e testadas  
✅ Observabilidade local funcionando (traces exportados em JSON)  
✅ Pydantic AI rodando com acesso a LLM  
✅ Dados convertidos e prontos para RAG  
✅ Environment de desenvolvimento reproduzível  

**Próxima Atividade:** TASK-004 - Implementação do RAG Local (Base de Conhecimento)
