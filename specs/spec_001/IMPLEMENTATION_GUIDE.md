# 🚀 Módulos Implementados - SPEC-003-1

## Setup Rápido

### 1. Instalar Dependências

```bash
# Ativar venv
source venv/bin/activate

# Instalar todas as dependências
pip install -r requirements.txt
```

### 2. Diretórios Necessários

Os seguintes diretórios serão criados automaticamente:

```bash
mkdir -p ./data/vectorstore
mkdir -p ./data/episodic_memory
mkdir -p ./observability/dashboards
```

---

## 📚 Exemplos de Uso

### 1. Observabilidade (OpenTelemetry)

```python
from src.observability import get_tracer, trace_agent_call
import time

# Método 1: Usando o tracer diretamente
tracer = get_tracer("meu_servico")

def minha_funcao():
    with tracer.start_as_current_span("operacao_importante") as span:
        span.set_attribute("user_id", "user_123")
        time.sleep(0.1)
        # Seu código aqui
    return "resultado"

# Método 2: Usando decorador (mais simples)
@trace_agent_call("processar_documento")
def processar(conteudo: str) -> str:
    return f"Processado: {conteudo}"

# Resultado: trace JSON em ./observability/dashboards/
```

### 2. RAG Local

```python
from src.rag import SemanticRetriever

# Inicializar
retriever = SemanticRetriever(db_path="./data/vectorstore")

# Indexar documento
stats = retriever.index_document(
    doc_id="doc_001",
    content="""
    Python é uma linguagem de programação versátil.
    Suporta múltiplos paradigmas e tem uma comunidade ativa.
    """,
    collection="conhecimento",
    metadata={"source": "wikipedia", "lang": "pt"}
)
print(stats)  # Mostra estatísticas de chunking

# Buscar
resultados = retriever.retrieve(
    query="Características de Python",
    collection="conhecimento",
    top_k=3
)

for resultado in resultados:
    print(f"ID: {resultado['id']}")
    print(f"Relevância: {resultado['relevance_score']}")
    print(f"Conteúdo: {resultado['content']}\n")

# Buscar agrupado por documento fonte
resultados_agrupados = retriever.retrieve_by_source(
    query="Python programming",
    group_by_source=True
)
```

### 3. Memória com Guardrails

```python
from src.memory import PIIGuardrails, SemanticMemory

# ========== Guardrails (Sanitização de PII) ==========

# Detecção
texto = "Meu CPF é 123.456.789-10 e email: joao@example.com"
pii_encontrado = PIIGuardrails.extract_pii(texto)
print(pii_encontrado)
# {'cpf': ['123.456.789-10'], 'email': ['joao@example.com']}

# Sanitização
texto_limpo = PIIGuardrails.sanitize(texto)
print(texto_limpo)
# "Meu CPF é [REDACTED]_CPF e email: [REDACTED]_EMAIL"

# Verificação
if PIIGuardrails.has_pii(texto):
    print("Aviso: Contém dados sensíveis!")

# ========== Memória Semântica ==========

memory = SemanticMemory(storage_path="./data/semantic_memory.json")

# Adicionar fatos
memory.add_fact(
    fact_id="python_001",
    content="Python é interpretado e dinamicamente tipado",
    keywords=["python", "tipagem", "linguagem"],
    confidence=0.95,
    source="documentation"
)

# Recuperar fato
fato = memory.get_fact("python_001")
print(fato)

# Buscar por palavra-chave
resultados = memory.search_by_keyword("python", exact_match=False)
print(f"Encontrados: {len(resultados)} fatos")

# Adicionar relações entre fatos
memory.add_fact("python_002", "Python usa indentação como sintaxe")
memory.add_relation("python_001", "python_002", relation_type="related")

# Recuperar relacionados
relacionados = memory.get_related_facts("python_001", relation_type="related")
print(f"Fatos relacionados: {relacionados}")

# Exportar
memory.export_to_json("./dados_exportados.json")

# Estatísticas
stats = memory.get_statistics()
print(f"Total de fatos: {stats['total_facts']}")
print(f"Conceitos únicos: {stats['total_concepts']}")
```

### 4. Memória Episódica (Histórico)

```python
from src.memory import EpisodicMemory
from datetime import datetime, timedelta

memory = EpisodicMemory(db_path="./data/episodic_memory.db")

# Registrar conversa
record_id = memory.add_conversation(
    user_id="user_123",
    user_msg="Como usar Python?",
    response="Python é uma linguagem de programação...",
    metadata={"language": "pt", "topic": "programming"},
    tokens_used=250
)

# Recuperar conversas recentes
conversas = memory.get_recent_conversations(user_id="user_123", limit=10)
for conv in conversas:
    print(f"User: {conv['user_message']}")
    print(f"Agent: {conv['agent_response']}\n")

# Buscar em intervalo de tempo
inicio = datetime.now() - timedelta(days=7)
fim = datetime.now()
conversas_semana = memory.get_conversations_between("user_123", inicio, fim)

# Estatísticas de usuário
stats = memory.get_user_statistics("user_123")
print(f"Total de conversas: {stats['total_conversations']}")
print(f"Tokens usados: {stats['total_tokens']}")

# Limpar conversas antigas (mais de 30 dias)
deletados = memory.cleanup_old_conversations(days_to_keep=30)
print(f"Limpas {deletados} conversas antigas")

# Exportar para JSON
memory.export_conversations("user_123", "./conversas_user_123.json")
```

### 5. Conversão de Dados

```bash
# Converter documentos DOCX/XLSX para Markdown
python3 scripts/convert_data.py ./data/cursos --output ./data/converted_docs

# Converter com opções
python3 scripts/convert_data.py ./data/referencias \
  --output ./data/md \
  --no-recursive  # Apenas raiz, não subdiretórios
```

### 6. Visualizar Traces

```bash
# Analisar traces gerados
python3 scripts/visualize_traces.py ./observability/dashboards

# Exportar análise
python3 scripts/visualize_traces.py ./observability/dashboards \
  --output ./trace_analysis.json
```

---

## 🔄 Pipeline Completo

```python
from src.observability import trace_agent_call
from src.rag import SemanticRetriever
from src.memory import PIIGuardrails, SemanticMemory

@trace_agent_call("pipeline_completo")
def processar_query_usuario(user_id: str, query: str):
    """Pipeline completo com todos os módulos."""
    
    # 1. Sanitizar entrada
    query_limpo = PIIGuardrails.sanitize(query)
    
    # 2. Buscar no RAG
    retriever = SemanticRetriever()
    contexto = retriever.retrieve(query_limpo, top_k=3)
    
    # 3. Construir resposta
    resposta = f"Baseado em: {contexto[0]['content']}" if contexto else "Sem contexto"
    
    # 4. Armazenar em memória
    memory = SemanticMemory()
    memory.add_fact(
        fact_id=f"{user_id}_{int(time.time())}",
        content=query_limpo,
        keywords=query_limpo.split(),
        source="user_query"
    )
    
    return resposta

# Usar
resultado = processar_query_usuario("user_123", "Como usar Python?")
print(resultado)
# Traces salvos automaticamente em ./observability/dashboards/
```

---

## 🧪 Testes

```bash
# Rodar testes de integração
python3 tests/test_spec_003_1.py

# Ou com pytest (se instalado)
pytest tests/test_spec_003_1.py -v
```

---

## 📊 Estrutura de Dados

### PII Detectados
- CPF: `123.456.789-10`
- Email: `user@example.com`
- Telefone: `(11) 98765-4321`
- Cartão de crédito: `1234 5678 9012 3456`
- IP: `192.168.1.1`
- SSN: `123-45-6789`

### Tipos de Metadados Suportados

```python
# No RAG
metadata = {
    "source": "documento.pdf",
    "author": "João Silva",
    "date": "2026-06-02",
    "language": "pt",
    "category": "research"
}

# Na memória semântica
metadata = {
    "source": "document_name",
    "confidence": 0.95,
    "language": "pt",
    "keywords": ["ai", "machine learning"]
}
```

---

## ⚙️ Configuração Avançada

### Customizar Tamanho de Chunks

```python
from src.rag import SemanticRetriever

retriever = SemanticRetriever(
    db_path="./custom_db",
    chunk_size=2000,  # Padrão: 1000
    chunk_overlap=400  # Padrão: 200
)
```

### Customizar Modelo de Embeddings

```python
from src.rag import VectorStore

store = VectorStore(
    db_path="./vectorstore",
    embedding_model="sentence-transformers/all-mpnet-base-v2"
    # Padrão: "sentence-transformers/all-MiniLM-L6-v2"
    # Alternativas: all-mpnet, all-distilroberta, paraphrase-* etc
)
```

### Patterns Customizados de PII

```python
from src.memory import PIIGuardrails

custom_patterns = {
    "data_hora": r"\d{4}-\d{2}-\d{2}",
    "cnpj": r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}"
}

guardrails = PIIGuardrails(additional_patterns=custom_patterns)
```

---

## 📈 Performance e Limitações

### Performance Esperada

| Operação | Tempo | Limite |
|----------|-------|--------|
| Indexar documento | ~100ms | 10MB por doc |
| Busca semântica | ~50ms | 100k documentos |
| Sanitizar PII | ~5ms | Sem limite |
| Adicionar fato | ~2ms | Sem limite |

### Recomendações

- **Chunk Size:** 500-2000 caracteres (padrão: 1000)
- **Chunk Overlap:** 10-30% do tamanho (padrão: 200)
- **Top-K:** 3-10 resultados (padrão: 5)
- **Limpeza de dados:** 30-90 dias (padrão: 30)

---

## 🆘 Troubleshooting

### "No module named 'chromadb'"
```bash
pip install chromadb>=0.4.0
```

### "No module named 'sentence_transformers'"
```bash
pip install sentence-transformers>=2.2.0
```

### "No module named 'sqlalchemy'"
```bash
pip install sqlalchemy>=2.0.0
```

### Jaeger não conecta
```python
from src.observability import init_tracer

# Inicializar sem Jaeger (só JSON)
init_tracer("meu_servico", use_jaeger=False)
```

---

## 📚 Documentação Adicional

- [OpenTelemetry Docs](https://opentelemetry.io/docs/)
- [ChromaDB Docs](https://docs.trychroma.com/)
- [sentence-transformers](https://www.sbert.net/)
- [SQLAlchemy ORM](https://docs.sqlalchemy.org/)

---

**Desenvolvido em 02 de Junho de 2026**
