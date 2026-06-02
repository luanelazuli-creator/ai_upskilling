# Setup do Projeto

## Pré-requisitos

- Python 3.9+
- Ollama instalado e rodando
- Git

## Passos

1. Clone o repositório
2. Execute `bash scripts/setup_venv.sh`
3. Ative venv: `source venv/bin/activate`
4. Copie `.env.example` para `.env`
5. Confirme que Ollama está rodando: `ollama serve` em outro terminal
6. Teste: `python -m src.main test-ollama`
7. Inicie o chat: `python -m src.main chat`

## Troubleshooting

### Ollama não está acessível
- Verifique se Ollama está rodando: `ollama serve`
- Confirme a URL em `.env`: `OLLAMA_BASE_URL=http://localhost:11434`

### Modelo não encontrado
- Liste modelos disponíveis: `ollama list`
- Baixe um modelo: `ollama pull mistral`

### Erro de importação
- Confirme que está no venv ativado
- Reinstale dependências: `pip install -r requirements.txt`
