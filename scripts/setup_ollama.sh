# 1. Copiar configuração
cp .env.example .env

# 2. Iniciar Ollama (em outro terminal)
ollama serve

# 3. Baixar modelo
ollama pull mistral

# 4. Testar agente
source venv/bin/activate
python -m src.main test-ollama