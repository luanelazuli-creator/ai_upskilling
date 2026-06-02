# Troubleshooting: Erro de Porta Ocupada (11434)

## ❌ Erro
```
Error: listen tcp 127.0.0.1:11434: bind: address already in use
```

## 🔍 Causa
A porta 11434 (padrão do Ollama) já está sendo usada por outra instância do Ollama que continua rodando ou não foi finalizada corretamente.

## ✅ Soluções

### 1. Verificar Instância Ativa (Diagnóstico)
```bash
# Listar processo usando porta 11434
lsof -i :11434

# Exemplo de saída:
# COMMAND  PID        USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
# ollama  1044 luanelazuli    3u  IPv4 0x27a0b5a...      0t0  TCP localhost:11434 (LISTEN)
```

### 2. Finalizar Instância Anterior
```bash
# Usando o PID encontrado acima (ex: 1044)
kill -9 1044

# Esperar um momento
sleep 2

# Verificar se a porta foi liberada
lsof -i :11434  # Deve retornar vazio
```

### 3. Iniciar Ollama Novamente
```bash
# Opção 1: Em foreground (verá logs)
ollama serve

# Opção 2: Em background
ollama serve &
```

### 4. Alternativa: Usar Porta Diferente
Se quiser manter a instância anterior, use outra porta:

**Em .env:**
```bash
OLLAMA_BASE_URL=http://localhost:11435  # Porta diferente
```

**Ao iniciar Ollama:**
```bash
OLLAMA_HOST=127.0.0.1:11435 ollama serve
```

## 🛠️ Script para Automatizar

Crie `scripts/cleanup_ollama.sh`:
```bash
#!/bin/bash
echo "Limpando instâncias anteriores do Ollama..."
PID=$(lsof -i :11434 | grep -oP '(?<=\s)\d+(?=\s)' | tail -1)
if [ -n "$PID" ]; then
    echo "Finalizando Ollama (PID: $PID)..."
    kill -9 $PID
    sleep 2
    echo "✓ Instância finalizada"
fi
echo "Iniciando Ollama..."
ollama serve
```

Depois:
```bash
bash scripts/cleanup_ollama.sh
```

## 📋 Checklist Rápido

- [ ] Verificar se Ollama está instalado: `which ollama`
- [ ] Buscar processo anterior: `lsof -i :11434`
- [ ] Finalizar processo: `kill -9 <PID>`
- [ ] Confirmar porta livre: `lsof -i :11434` (vazio)
- [ ] Iniciar Ollama: `ollama serve`
- [ ] Testar agente: `python -m src.main test-ollama`

## ✅ Testes Realizados

1. **Porta antes:** 11434 estava ocupada (PID 1044)
2. **Ação:** Finalizamos o processo com `kill -9 1044`
3. **Porta depois:** Liberada com sucesso
4. **Ollama:** Iniciado novamente automaticamente
5. **Agente:** Funcionando com modelo `tinyllama` ✅

## 📊 Status Final

```
Port Status:     ✅ Livre e operacional (11434)
Ollama Status:   ✅ Rodando
Modelo:          ✅ tinyllama disponível
Agente:          ✅ Gerando respostas com sucesso
```
