# Setup do Ollama

## Instalação

```bash
# macOS (via Homebrew)
brew install ollama

# ou baixe de https://ollama.ai
```

## Iniciar Ollama

```bash
ollama serve
```

## Baixar Modelo

Em outro terminal:
```bash
# Mistral (7B - recomendado para rápido)
ollama pull mistral

# ou Llama 2
ollama pull llama2
```

## Testar

```bash
curl http://localhost:11434/api/generate -d '{
  "model": "mistral",
  "prompt": "Olá"
}'
```
