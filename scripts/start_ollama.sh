#!/bin/bash

# Script para resolver conflito de porta do Ollama
# Se a porta 11434 estiver em uso, mata o processo anterior e inicia novo

OLLAMA_PORT=11434

echo "🔍 Verificando porta $OLLAMA_PORT..."

# Verificar se há processo usando a porta
PID=$(lsof -i :$OLLAMA_PORT 2>/dev/null | grep -oP '(?<=\s)\d+(?=\s)' | tail -1)

if [ -n "$PID" ]; then
    echo "⚠️  Processo Ollama anterior encontrado (PID: $PID)"
    echo "Finalizando..."
    kill -9 $PID 2>/dev/null
    sleep 2
    echo "✓ Processo finalizado"
fi

# Verificar se porta está livre
if lsof -i :$OLLAMA_PORT >/dev/null 2>&1; then
    echo "❌ Porta ainda ocupada. Tente novamente em alguns segundos."
    exit 1
fi

echo "✓ Porta $OLLAMA_PORT está livre"
echo "🚀 Iniciando Ollama..."
echo ""

ollama serve
