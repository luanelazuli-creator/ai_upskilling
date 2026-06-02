#!/bin/bash

# Script para finalizar instância do Ollama
# Mata o processo que está usando a porta 11434

OLLAMA_PORT=11434

echo "🔍 Procurando por instâncias do Ollama na porta $OLLAMA_PORT..."

# Encontrar PID do processo usando a porta
PID=$(lsof -i :$OLLAMA_PORT 2>/dev/null | grep -oP '(?<=\s)\d+(?=\s)' | tail -1)

if [ -n "$PID" ]; then
    echo "❌ Processo Ollama encontrado (PID: $PID)"
    echo "Finalizando..."
    kill -9 $PID 2>/dev/null
    sleep 1
    
    # Verificar se foi finalizado
    if lsof -i :$OLLAMA_PORT >/dev/null 2>&1; then
        echo "⚠️  Falha ao finalizar. Tente com sudo: sudo kill -9 $PID"
        exit 1
    else
        echo "✓ Processo finalizado com sucesso"
        echo "✓ Porta $OLLAMA_PORT está livre"
    fi
else
    echo "ℹ️  Nenhum processo Ollama encontrado na porta $OLLAMA_PORT"
fi
