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
echo "2. Garantir que Ollama está rodando:"
echo "   - Verifique instâncias ativas: lsof -i :11434"
echo "   - Se houver conflito: kill <PID>"
echo "   - Inicie: ollama serve"
echo "3. Baixar modelo (se necessário):"
echo "   - ollama pull tinyllama  (ou mistral, llama2, neural-chat)"
echo "4. Testar agente: python -m src.main test-ollama"
echo "5. Iniciar chat: python -m src.main chat"
