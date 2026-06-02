# Second Brain - AI Upskilling Project

Projeto de aprendizado e desenvolvimento de agentes de IA com Pydantic AI e Ollama.

## Visão Geral

Este projeto implementa um assistente pessoal inteligente que ajuda na produtividade e gestão de conhecimento, utilizando modelos locais via Ollama.

## Quick Start

```bash
# 1. Setup do ambiente
bash scripts/setup_venv.sh

# 2. Ativar ambiente virtual
source venv/bin/activate

# 3. Configurar variáveis
cp .env.example .env

# 4. Iniciar Ollama em outro terminal
ollama serve

# 5. Testar agente
python -m src.main test-ollama

# 6. Chat interativo
python -m src.main chat
```

## Estrutura do Projeto

```
ai_upskilling/
├── README.md                          (documentação principal)
├── requirements.txt                   (dependências Python)
├── .env.example                       (template de variáveis)
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
│   └── OLLAMA_SETUP.md                (guia de Ollama)
│
└── scripts/
    └── setup_venv.sh                  (criar ambiente virtual)
```

## Documentação

- [SETUP.md](docs/SETUP.md) - Guia de configuração detalhado
- [OLLAMA_SETUP.md](docs/OLLAMA_SETUP.md) - Setup do Ollama

## Testes

```bash
# Executar todos os testes
pytest

# Executar com verbosidade
pytest -v

# Testar somente conexão com Ollama
python -m src.main test-ollama
```

## Próximos Passos

- Observabilidade e setup avançado (TASK-003-1)
- Integração com bancos de dados
- Melhorias na memória do agente
