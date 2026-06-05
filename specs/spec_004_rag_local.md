# Engenharia de Especificação: SPEC-004
## RAG Local — Integração Completa com os 3 Domínios

**ID da Atividade:** TASK-004
**Data de Criação:** 05 de Junho de 2026
**Status:** 🟡 Em Refinamento
**Autor:** Desenvolvedor Capstone
**Depende de:** SPEC-MEM, SPEC-003-2
**Substitui parcialmente:** SPEC-002 §3.5 (frontmatter), SPEC-003-1 (`scripts/convert_data.py` e `src/rag/*`)

---

### 1. Visão Geral e Escopo

Esta spec é **autoritativa** sobre:
1. O contrato de saída do pré-processamento (`.md` + frontmatter YAML por domínio).
2. O pipeline completo de ingestão: pré-processar → chunkar → embedar → persistir.
3. A API de busca semântica consumida pelos agentes.

Consome o `PersistentClient` ChromaDB unificado definido na SPEC-003-2 §5.

#### Em escopo
- Pré-processamento dos formatos brutos (`.docx`, `.csv`, `.xlsx`) para `.md` com frontmatter
- Chunking adaptativo por domínio
- Embeddings com modelo multilingual
- Indexação nas coleções `diario`, `cursos`, `referencias`
- Detecção de modificações via hash SHA-256 para re-indexação incremental
- Sanitização de PII na ingestão
- API `SemanticRetriever.retrieve(...)` consumida por SPEC-006 (Agente 2)

#### Fora de escopo
- Indexação de `episodic_conversations` e `user_facts` (já coberto pela SPEC-003-2)
- Implementação dos agentes que **consomem** o RAG (SPEC-005/006/007)
- Otimização de performance além do MVP

---

### 2. Pipeline de Ingestão End-to-End

```
┌──────────────────────────────────────────────────────────┐
│ ./data/{dominio}/  (arquivos brutos .docx/.csv/.xlsx/.md) │
└────────────────────────┬──────────────────────────────────┘
                         ↓
        ┌────────────────────────────────────────┐
        │ 1. Discovery                            │
        │    Varredura recursiva por extensões    │
        │    suportadas                           │
        └────────────────┬───────────────────────┘
                         ↓
        ┌────────────────────────────────────────┐
        │ 2. Pré-processamento                    │
        │    .docx → .md (python-docx)            │
        │    .csv  → .md (pandas → tabela)        │
        │    .xlsx → .md (pandas → tabela ou      │
        │              linha-por-linha; ver §4)   │
        │    .md   → passa direto                 │
        │    Aplica frontmatter conforme §3       │
        └────────────────┬───────────────────────┘
                         ↓
        ┌────────────────────────────────────────┐
        │ 3. Parse                                │
        │    Separa frontmatter (YAML) do corpo   │
        │    Calcula hash SHA-256 do corpo        │
        └────────────────┬───────────────────────┘
                         ↓
        ┌────────────────────────────────────────┐
        │ 4. Detecção de mudança                  │
        │    Compara hash com hash armazenado     │
        │    no ChromaDB. Se igual: skip.         │
        │    Se diferente ou ausente: continua.   │
        └────────────────┬───────────────────────┘
                         ↓
        ┌────────────────────────────────────────┐
        │ 5. Sanitização de PII                   │
        │    Guardrails.sanitize() no corpo       │
        │    Loga PII encontrado em span OTel     │
        └────────────────┬───────────────────────┘
                         ↓
        ┌────────────────────────────────────────┐
        │ 6. Chunking adaptativo (ver §4)         │
        │    Diário: arquivo = 1 chunk            │
        │    Cursos/Referências: 1000/200         │
        │    Planilhas: linha = 1 chunk           │
        └────────────────┬───────────────────────┘
                         ↓
        ┌────────────────────────────────────────┐
        │ 7. Embedding + Persistência             │
        │    paraphrase-multilingual-MiniLM-L12-v2│
        │    Coleção por domínio                 │
        │    Delete prévio se hash mudou          │
        └────────────────┬───────────────────────┘
                         ↓
        ┌────────────────────────────────────────┐
        │ 8. Log de ingestão (OTel span)          │
        │    {domain, file, chunks, duration_ms,  │
        │     pii_found, hash}                    │
        └────────────────────────────────────────┘
```

---

### 3. Contratos de Frontmatter por Domínio

**Regra geral:** todo `.md` gerado pelo pré-processamento começa com frontmatter YAML delimitado por `---`. Campos em **negrito** são obrigatórios.

#### 3.1 Diário (`/data/diario/YYYY/MM/`)

```yaml
---
type: diario                          # OBRIGATÓRIO; valor fixo
date: 2026-06-11                      # OBRIGATÓRIO; ISO 8601, derivado do nome do arquivo
source_file: "Dia 11 - Keep Studying.docx"   # OBRIGATÓRIO
tags: [keep_studying, mcp]            # OPCIONAL; extraído heuristicamente do título
ingested_at: 2026-06-05T10:00:00Z     # OBRIGATÓRIO; gerado na ingestão
content_hash: "sha256:abc123..."      # OBRIGATÓRIO; do corpo (sem frontmatter)
---
```

#### 3.2 Cursos (`/data/cursos/`)

```yaml
---
type: course                          # OBRIGATÓRIO
course: "Data Engineer Certificate"   # OBRIGATÓRIO; extraído do nome ou conteúdo
status: em_andamento                  # OPCIONAL; valores: em_andamento | concluido | planejado
last_updated: 2026-06-02              # OPCIONAL
source_file: "Data Engineer Certificate.docx"  # OBRIGATÓRIO
ingested_at: 2026-06-05T10:00:00Z     # OBRIGATÓRIO
content_hash: "sha256:..."            # OBRIGATÓRIO
---
```

**Caso especial — Golden Prompts:** arquivos em `cursos/Golden Prompts/` recebem `type: golden_prompt` em vez de `type: course`. Isso prepara o terreno para futura Procedural Memory (SPEC-MEM §2.4).

#### 3.3 Referências (`/data/referencias/`)

```yaml
---
type: reference                       # OBRIGATÓRIO
category: stakeholders                # OBRIGATÓRIO; valores: manuais | stakeholders | glossario | procedimentos
source_file: "Thoughtworks contacts.xlsx"  # OBRIGATÓRIO
last_reviewed: 2026-06-02             # OPCIONAL
ingested_at: 2026-06-05T10:00:00Z     # OBRIGATÓRIO
content_hash: "sha256:..."            # OBRIGATÓRIO
---
```

**Mapeamento `source_file → category` (default; pode ser sobrescrito manualmente):**

| Arquivo | Category |
|---|---|
| `Acessos sistemas.docx`, `Atestados.docx` | `manuais` |
| `Glossário.xlsx` | `glossario` |
| `Links Úteis.xlsx` | `procedimentos` |
| `Pessoas Importantes.xlsx`, `Thoughtworks contacts.xlsx` | `stakeholders` |

---

### 4. Estratégia de Chunking Adaptativo

| Domínio | Tipo de arquivo | Estratégia | Justificativa |
|---|---|---|---|
| **Diário** | `.md` (1 dia) | **1 chunk por arquivo** | Arquivos são curtos (~200-500 palavras); fragmentar perde contexto temporal coeso |
| **Cursos** | `.md` (curso/certificado) | Chunking padrão (1000 chars / 200 overlap) | Conteúdo de aprendizado é estruturado em seções; chunk médio preserva ideias |
| **Cursos** | `golden_prompt` | **1 chunk por arquivo** | Prompts são unidades semânticas atômicas |
| **Referências (manuais)** | `.docx` → `.md` | Chunking padrão (1000/200) | Manuais são longos; chunking médio |
| **Referências (planilhas)** | `.xlsx`/`.csv` | **1 chunk por linha** | Cada linha é uma entidade independente (1 stakeholder, 1 termo de glossário, 1 link) |

#### 4.1 Detalhe — Chunking de Planilhas

Para `.xlsx`/`.csv`:

1. Cabeçalhos da primeira linha viram **chaves de metadata**.
2. Cada linha subsequente vira **um chunk**.
3. O `content` do chunk é a serialização textual das colunas:
   `"<col1>: <val1>. <col2>: <val2>. ...".`
4. Metadata do chunk inclui:
   - `row_index` (int)
   - `source_file` (string)
   - Todas as colunas como `field_<nome>` (permite filtros estruturados via ChromaDB)

**Exemplo — `Glossário.xlsx` com colunas `Termo | Definição | Categoria`:**

| row_index | Content do chunk | Metadata adicional |
|---|---|---|
| 1 | `"Termo: RAG. Definição: Retrieval-Augmented Generation. Categoria: AI."` | `field_termo: "RAG"`, `field_categoria: "AI"` |

**Nota:** os nomes das colunas reais dos arquivos serão confirmados quando os dados forem acessíveis. A spec define o **padrão**, não o schema específico de cada planilha.

---

### 5. Embedding Model

**Modelo escolhido:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

**Justificativa:**
- Dados em PT-BR; modelo all-MiniLM-L6-v2 (atual default) é treinado predominantemente em inglês.
- Suporte oficial a 50+ idiomas incluindo português.
- Dimensão do embedding: 384 (mesmo que all-MiniLM-L6-v2 — compatível com ChromaDB default).
- Tamanho: ~120MB (vs ~80MB do anterior); custo aceitável.

**Configuração via `.env` (atualizar SPEC-003-2 §4):**

```bash
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
```

**Override programático:** `VectorStore(embedding_model="...")` continua funcionando, útil para evals comparativos (SPEC-009).

---

### 6. Re-indexação Incremental via Hash SHA-256

#### 6.1 Cálculo

`content_hash = sha256(corpo_sem_frontmatter).hexdigest()`

O hash cobre **apenas o corpo** — alterações em metadata (ex: `ingested_at`) não invalidam o cache.

#### 6.2 Armazenamento

Cada chunk no ChromaDB carrega `content_hash` no metadata (o mesmo hash para todos os chunks de um mesmo arquivo).

#### 6.3 Algoritmo de re-indexação

```
para cada arquivo em discovery:
    novo_hash = sha256(corpo)
    chunks_existentes = chromadb.get(where={source_file: arquivo})

    se chunks_existentes está vazio:
        # arquivo novo → indexar
        chunk + embed + insert

    senão se chunks_existentes[0].metadata.content_hash == novo_hash:
        # inalterado → skip
        continue

    senão:
        # arquivo modificado → invalidar e reindexar
        chromadb.delete(where={source_file: arquivo})
        chunk + embed + insert
```

#### 6.4 Modo `--force`

CLI da ingestão expõe `--force` que ignora hash check e reindexa tudo. Útil para mudanças no chunking strategy ou no embedding model.

---

### 7. Sanitização de PII na Ingestão

Conforme SPEC-MEM §6, **PII é sanitizado antes da escrita** no ChromaDB.

#### 7.1 Política por domínio

| Domínio | Sanitização agressiva? | Justificativa |
|---|---|---|
| Diário | **Sim** | Pode conter nomes de clientes, detalhes sensíveis |
| Cursos | **Sim** | Pode conter nomes pessoais em notas |
| Referências/manuais | **Sim** | Manuais corporativos podem mencionar credenciais |
| Referências/stakeholders | **Não** (mascarar apenas emails/telefones) | A função do arquivo é manter contatos; sanitizar agressivo destruiria valor |
| Referências/glossario | **Sim** | Não deveria ter PII; sanitizar por segurança |

**Decisão de design:** stakeholders mascaram **emails e telefones** (substituindo por placeholders determinísticos `[STAKEHOLDER_EMAIL_<row_index>]`) para permitir buscas semânticas por nome/cargo sem expor contato direto na collection.

#### 7.2 Observabilidade

Cada ingestão de arquivo gera span OTel com:
```
attributes:
  - domain: <diario|cursos|referencias>
  - source_file: <path>
  - pii_types_found: ["cpf", "email", ...]
  - pii_count: <int>
  - chunks_created: <int>
  - duration_ms: <float>
```

Consumido por SPEC-009 para métrica de PII Leak Rate.

---

### 8. API de Busca (consumida pelos agentes)

```python
class SemanticRetriever:
    def retrieve(
        query: str,
        collection: Literal["diario", "cursos", "referencias"],
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,  # ChromaDB where-clause
    ) -> List[RAGChunk]

    def retrieve_multi_collection(
        query: str,
        collections: List[str],
        top_k_per_collection: int = 3,
    ) -> Dict[str, List[RAGChunk]]
```

#### 8.1 Filtros suportados (consultados pelo Agente 1)

| Filtro | Coleção | Exemplo |
|---|---|---|
| `{"date": {"$gte": "2026-06-01", "$lte": "2026-06-30"}}` | `diario` | "o que fiz em junho" |
| `{"type": "golden_prompt"}` | `cursos` | "qual prompt usar para X" |
| `{"category": "stakeholders"}` | `referencias` | "quem é responsável por Y" |
| `{"course": "Data Engineer Certificate"}` | `cursos` | "onde parei no DE" |

#### 8.2 RAGChunk

```python
@dataclass
class RAGChunk:
    id: str
    content: str
    collection: str
    relevance_score: float       # 1 - cosine_distance
    metadata: Dict[str, Any]     # frontmatter + chunk_index + content_hash
```

---

### 9. Arquivos Impactados

| Arquivo | Operação | Notas |
|---|---|---|
| `scripts/convert_data.py` | **Reescrita** | Aplica frontmatter conforme §3; sanitização PII; calcula hash |
| `scripts/ingest.py` | **Criar** | Pipeline orquestrador end-to-end com `--force` |
| `src/rag/store.py` | Refatoração | Embedding model trocado; helpers para hash check |
| `src/rag/vectorizer.py` | Refatoração | Implementar chunking adaptativo (§4) |
| `src/rag/retriever.py` | Refatoração | API conforme §8 (multi-collection) |
| `src/rag/preprocessing/` | **Criar diretório** | Módulos por formato: `docx.py`, `xlsx.py`, `csv.py`, `frontmatter.py` |
| `src/config.py` | Adicionar settings | EMBEDDING_MODEL, paths de dados |
| `.env.example` | Adicionar EMBEDDING_MODEL | — |
| `tests/test_spec_004.py` | **Criar** | Cobertura do pipeline §9 |
| `specs/spec_002_pipeline_ingestao.md` | Nota de superseded | "§3.5 (frontmatter) refinado pela SPEC-004 §3" |

---

### 10. Plano de Testes

#### 10.1 Pré-processamento
- `test_docx_to_md_preserves_headings` — `H1`/`H2`/`H3` viram `#`/`##`/`###`
- `test_xlsx_row_becomes_chunk` — planilha com 5 linhas gera 5 chunks
- `test_csv_handled_identically_to_xlsx` — paridade entre formatos tabulares
- `test_frontmatter_generated_per_domain` — campos obrigatórios estão presentes
- `test_content_hash_deterministic` — mesmo input → mesmo hash

#### 10.2 Chunking adaptativo
- `test_diario_one_chunk_per_file` — arquivo do diário gera exatamente 1 chunk
- `test_cursos_standard_chunking` — texto longo é fragmentado em ~1000-char chunks
- `test_golden_prompt_one_chunk_per_file` — golden prompts não são fragmentados
- `test_reference_spreadsheet_row_chunks` — cada linha = 1 chunk

#### 10.3 Re-indexação
- `test_unchanged_file_skipped` — hash igual → sem reindex
- `test_modified_file_reindexed` — mudança no corpo → delete+insert
- `test_force_flag_reindexes_unchanged` — `--force` ignora cache
- `test_new_file_indexed` — arquivo sem chunks anteriores entra normalmente

#### 10.4 Sanitização
- `test_pii_sanitized_before_chromadb_write` — corpo persistido não contém PII
- `test_stakeholders_only_mask_email_phone` — política específica do domínio
- `test_pii_span_emitted` — span OTel é gerado com tipos encontrados

#### 10.5 Busca
- `test_retrieve_returns_top_k_ordered_by_score` — ordenação por relevance_score desc
- `test_filter_by_date_range_on_diario` — query temporal
- `test_filter_by_category_on_referencias` — query estruturada
- `test_multi_collection_returns_dict_per_collection` — API multi-collection

---

### 11. Política de Erro

| Cenário | Comportamento |
|---|---|
| Arquivo `.docx` corrompido | Log de erro com span OTel; pula arquivo; **não interrompe** pipeline |
| Frontmatter YAML inválido em `.md` já existente | Log warning; tenta re-gerar; se falhar, pula |
| ChromaDB indisponível | `RuntimeError` imediato; pipeline aborta |
| Hash check sem `source_file` no metadata (legado) | Tratar como "arquivo novo" — força ingestão |
| Coleção não existe em retrieve | Criar vazia + retornar lista vazia (idempotência) |

---

### 12. Checklist de Aceite

#### Pré-implementação
- [x] Pipeline de 8 etapas definido (§2)
- [x] Frontmatter contratado por domínio (§3)
- [x] Chunking adaptativo formalizado (§4)
- [x] Modelo de embedding justificado (§5)
- [x] Hash check definido (§6)
- [x] Política de PII por domínio (§7)
- [x] API de busca contratada (§8)
- [x] Arquivos impactados listados (§9)
- [x] Plano de testes esboçado (§10)
- [ ] Spec revisada e aprovada para implementação

#### Implementação (futura)
- [ ] Módulos de pré-processamento em `src/rag/preprocessing/`
- [ ] `scripts/ingest.py` orquestrador com `--force`
- [ ] Refatoração de `store.py`, `vectorizer.py`, `retriever.py`
- [ ] Modelo multilingual baixado e funcionando
- [ ] 3 coleções populadas com os 11 arquivos existentes
- [ ] Suite de testes da §10 verde
- [ ] Smoke: query "o que fiz em junho?" retorna chunks do diário
- [ ] Smoke: query "quem é stakeholder X?" retorna chunks de referências

---

### 13. Estimativa de Esforço

| Fase | Estimativa |
|---|---|
| Refatorar pré-processamento (DOCX/XLSX/CSV + frontmatter) | 3h |
| Implementar chunking adaptativo | 1.5h |
| Setup do modelo multilingual + cache | 0.5h |
| Hash check + re-indexação incremental | 1.5h |
| Sanitização de PII na ingestão (incl. política stakeholders) | 1h |
| Refatorar retriever (multi-collection + filters) | 1h |
| Script `ingest.py` orquestrador | 1h |
| Testes (§10) | 2.5h |
| Smoke tests + ajustes | 1h |
| **Total** | **~13h** |

---

### 14. Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Heurística de extração de `date` do nome do arquivo do diário falha em formatos variantes | Média | Logar warning; permitir override manual via frontmatter pré-existente |
| Sanitização agressiva remove demais e degrada recall | Média | SPEC-009 mede; iteração orientada por evals |
| Modelo multilingual tem qualidade inferior em PT-BR específico do domínio | Baixa | Permite override via `EMBEDDING_MODEL`; SPEC-009 mede |
| Hash check falha silenciosamente (chunks com hash divergente no mesmo arquivo) | Baixa | Teste explícito; janela de invariante na §6 |
| Planilhas reais têm colunas variáveis que quebram o schema generico | Média | Spec define padrão; ajuste por arquivo se necessário ao acessar dados reais |

---

### 15. Dependências e Sequência

**Esta spec depende de:** SPEC-MEM, SPEC-003-2 (ChromaDB unificado).

**Esta spec é pré-requisito de:**
- **SPEC-006** (Agente 2 — síntese) consome `SemanticRetriever.retrieve()`.
- **SPEC-005** (Agente 1 — triagem) consome filtros estruturados (date, category, course).
- **SPEC-009** (Evals) usa o pipeline para gerar dataset de teste e medir métricas de RAG.

**Atividade subsequente recomendada:** SPEC-005 (Agente 1 — Triagem e Contexto Temporal).
