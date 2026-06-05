# Engenharia de Especificação: SPEC-003-2
## Migração dos Módulos de Memória Existentes

**ID da Atividade:** TASK-003-2
**Data de Criação:** 05 de Junho de 2026
**Status:** 🟡 Em Refinamento
**Autor:** Desenvolvedor Capstone
**Depende de:** SPEC-MEM (arquitetura de memória)
**Substitui parcialmente:** SPEC-003-1 §6 (módulos de memória)

---

### 1. Visão Geral

Refatorar os módulos `SemanticMemory` e `EpisodicMemory` implementados na SPEC-003-1 para aderir aos contratos definidos na SPEC-MEM. A migração é **só de código** — não há dados a preservar, porque:

1. Os arquivos brutos (`.docx`, `.csv`, `.xlsx`) estão em outro ambiente e precisam ser reprocessados de qualquer forma (alimenta a SPEC-004).
2. JSON/SQLite eventualmente existentes da SPEC-003-1 são descartados na primeira execução pós-migração.

Esta spec **não implementa** o Agente 3 (escopo da SPEC-007). Define apenas a camada de storage que o Agente 3 vai consumir.

---

### 2. Escopo

#### Em escopo
- Reescrita de `src/memory/semantic.py` para ChromaDB (coleção `user_facts`)
- Extensão de `src/memory/episodic.py` para usar ChromaDB (coleção `episodic_conversations`) + SQLite (metadata)
- Configuração de `USER_ID` e `SESSION_ID` via `.env`
- Unificação de `PersistentClient` ChromaDB com o RAG (mesma pasta, coleções diferentes)
- Atualização de testes existentes + novos testes para os contratos da SPEC-MEM

#### Fora de escopo
- Implementação do Agente 3 (SPEC-007)
- Lógica de extração de fatos a partir de conversas (SPEC-007)
- Working Memory (SPEC-008 — vive no orquestrador)
- Procedural Memory (roadmap)
- Migração de dados antigos (não há)

---

### 3. Diff de Contrato (Antes → Depois)

#### 3.1 SemanticMemory

| Aspecto | SPEC-003-1 (antes) | SPEC-MEM/003-2 (depois) |
|---|---|---|
| Storage | JSON file (`semantic_memory.json`) | ChromaDB coleção `user_facts` |
| Busca | Keyword matching (case-insensitive) | Vetorial (cosine similarity) |
| Schema do fato | `{fact_id, content, keywords[], confidence, source, timestamp}` | `{fact_id, user_id, content, category, source_conversation_id, confidence, timestamp}` |
| Relações entre fatos | `add_relation()`, `get_related_facts()` | **Removidas** |
| Keywords explícitas | Sim, array no schema | **Removidas** (embedding cobre) |
| Multi-tenancy | Não | Sim (`user_id` obrigatório em todas as APIs) |
| Categoria | Sim, opcional | Sim, opcional (ex: `preference`, `profile`, `context`) |
| `source` | String livre | `source_conversation_id` (FK opcional para Episodic) |

**APIs removidas:**
- `add_relation(fact_a, fact_b, relation_type)`
- `get_related_facts(fact_id, relation_type)`
- `search_by_keyword(...)` (busca semântica substitui)
- `export_to_json(...)` (debug pode usar coleção ChromaDB direto)

**APIs preservadas (com nova assinatura):**
- `add_fact(user_id, content, category, source_conversation_id, confidence) → fact_id`
- `search(user_id, query, top_k=3) → List[Fact]` (agora vetorial)
- `delete_fact(fact_id)` (direito de esquecimento)
- `list_by_category(user_id, category) → List[Fact]`
- `get_statistics(user_id) → Dict` (mantém para observabilidade)

#### 3.2 EpisodicMemory

| Aspecto | SPEC-003-1 (antes) | SPEC-MEM/003-2 (depois) |
|---|---|---|
| Storage | SQLite puro | SQLite (metadata) + ChromaDB (busca semântica) |
| Schema SQLite | `(id, user_id, timestamp, user_message, agent_response, metadata)` | `(id, user_id, session_id, timestamp, intent, pii_sanitized)` |
| Texto da conversa | SQLite (colunas `user_message`, `agent_response`) | ChromaDB (documento embedded como `"user: ... | agent: ..."`) |
| Busca | Filtro temporal + recência | Filtro temporal/usuário (SQLite) + match semântico (ChromaDB) |
| `session_id` | Não existe | Obrigatório |
| `intent` | Não existe | Opcional (atribuído pelo Agente 1; null se ausente) |
| `pii_sanitized` | Não existe | Obrigatório (flag de auditoria) |
| Tokens used | Sim, opcional | Mover para `metadata` JSON; não é parte do contrato canônico |

**APIs removidas:**
- Busca implícita por content via SQL LIKE (substitui por search_semantic)

**APIs preservadas (com nova assinatura):**
- `add_conversation(user_id, session_id, user_message, agent_response, intent, pii_sanitized) → ConversationId`
- `search_semantic(user_id, query, top_k=5, time_window=None) → List[ConversationRecord]` (nova)
- `get_recent(user_id, n=5) → List[ConversationRecord]`
- `get_conversations_between(user_id, start, end) → List[ConversationRecord]`
- `cleanup(retention_days=90) → int`
- `get_user_statistics(user_id) → Dict`

**Nota de integridade referencial:** o `id` do registro SQLite deve ser **idêntico** ao `id` do documento na coleção ChromaDB. Toda escrita/leitura passa por ambos atomicamente (ver §6).

---

### 4. Configuração via `.env`

Adicionar ao `.env.example` (e correspondentemente ao `src/config.py`):

```bash
# Identidade do Usuário (single-user no MVP)
USER_ID=luane              # Identificador estável do usuário
SESSION_ID=                # Opcional; se vazio, gerado como UUID por execução

# Memória — Paths
VECTORSTORE_PATH=./data/vectorstore       # Unificado: RAG + Memory
EPISODIC_METADATA_DB=./data/episodic_metadata.db   # SQLite com metadata indexável

# Memória — Coleções ChromaDB (constantes; expostas para overrides em teste)
COLLECTION_USER_FACTS=user_facts
COLLECTION_EPISODIC=episodic_conversations

# Memória — Retenção
EPISODIC_RETENTION_DAYS=90
```

**Comportamento de `SESSION_ID`:**
- Se definido no `.env`: usado como-é (útil para testes reprodutíveis).
- Se vazio/ausente: orquestrador gera UUID v4 na inicialização da sessão CLI.

---

### 5. Layout do ChromaDB Unificado

```
./data/vectorstore/         (chromadb.PersistentClient único)
├── chroma.sqlite3
├── ... (internos do ChromaDB)
│
└── Coleções:
    ├── diario                       ← RAG (SPEC-004)
    ├── cursos                       ← RAG (SPEC-004)
    ├── referencias                  ← RAG (SPEC-004)
    ├── episodic_conversations       ← Memory (esta spec)
    └── user_facts                   ← Memory (esta spec)
```

**Justificativa:** uma conexão por processo, backup unificado, mas isolamento via coleções (ownership conforme SPEC-MEM §3).

---

### 6. Atomicidade Episodic (ChromaDB + SQLite)

Como Episodic escreve em dois stores, define-se o **invariante**:

> Toda chamada de `add_conversation()` resulta em **exatamente um registro em cada store** (SQLite e ChromaDB), com o mesmo `id`.

**Estratégia de implementação (a detalhar em código):**
1. Gerar `id = uuid4()` no início.
2. Tentar escrever em ChromaDB primeiro (mais provável de falhar por dependência externa).
3. Se sucesso, escrever em SQLite.
4. Se SQLite falhar: deletar de ChromaDB (compensação).
5. Se ChromaDB falhar: levantar exceção, nada escrito.

**Não é transação ACID** — é compensação best-effort. Inconsistências serão detectadas por job de verificação periódica (fora do escopo da 003-2; documentar como follow-up).

---

### 7. Arquivos Impactados

| Arquivo | Operação | Notas |
|---|---|---|
| `src/memory/semantic.py` | **Reescrita completa** | API nova; remove relations/keywords |
| `src/memory/episodic.py` | **Refatoração** | Mantém SQLite; adiciona ChromaDB; novos campos |
| `src/memory/__init__.py` | Atualizar exports | Remove `add_relation` etc dos re-exports |
| `src/config.py` | Adicionar settings | USER_ID, SESSION_ID, paths, retention |
| `.env.example` | Adicionar variáveis | Conforme §4 |
| `tests/test_spec_003_1.py` | **Reescrever testes de memória** | Manter testes de Guardrails/Chunker como estão |
| `tests/test_spec_003_2.py` | **Criar** | Testes específicos dos novos contratos |
| `requirements.txt` | Nenhuma mudança | ChromaDB e SQLAlchemy já presentes |
| `specs/spec_003_1_observabilidade_avancado.md` | Adicionar nota de superseded | "§6 desta spec é refinado por SPEC-003-2" |

---

### 8. Plano de Testes

#### 8.1 SemanticMemory
- `test_add_fact_persists_to_chromadb` — fato gravado é recuperável por ID
- `test_search_finds_semantically_similar` — query "linguagem de programação" recupera fato sobre "Python"
- `test_search_isolates_by_user_id` — fato do user A não aparece em busca do user B
- `test_delete_fact_removes_from_collection` — direito de esquecimento
- `test_list_by_category_filters_correctly` — filtros por category funcionam

#### 8.2 EpisodicMemory
- `test_add_conversation_writes_both_stores` — invariante de atomicidade (§6)
- `test_atomicity_rollback_on_sqlite_failure` — simular falha SQLite e validar limpeza ChromaDB
- `test_search_semantic_with_time_window` — filtro temporal + match semântico combinados
- `test_get_recent_returns_chronological` — ordenação por timestamp desc
- `test_cleanup_respects_retention_days` — registros antigos removidos de ambos os stores
- `test_pii_sanitized_flag_required` — escrita sem flag levanta erro de contrato

#### 8.3 Configuração
- `test_session_id_generated_when_not_set` — UUID gerado quando `.env` não define
- `test_session_id_from_env_used_as_is` — `.env` vence default

#### 8.4 Preservados da SPEC-003-1
- Todos os testes de `PIIGuardrails` permanecem
- Todos os testes de `DocumentChunker` permanecem

---

### 9. Política de Erro

| Cenário | Comportamento esperado |
|---|---|
| `add_conversation()` sem `pii_sanitized=True` ou `=False` explícito | `ValueError` — flag obrigatória |
| `search()` em SemanticMemory sem `user_id` | `TypeError` (assinatura obriga) |
| ChromaDB indisponível na inicialização | `RuntimeError` com mensagem clara |
| Fact ID inexistente em `delete_fact()` | Silenciosamente no-op (idempotência) |
| `SESSION_ID` definido mas inválido (não-UUID) | Aceitar como string opaca; warning no log |

---

### 10. Checklist de Aceite

#### Pré-implementação (esta spec)
- [x] Diff de contrato documentado (§3)
- [x] Variáveis `.env` definidas (§4)
- [x] Layout ChromaDB unificado descrito (§5)
- [x] Política de atomicidade definida (§6)
- [x] Arquivos impactados listados (§7)
- [x] Plano de testes esboçado (§8)
- [x] Política de erro definida (§9)
- [ ] Spec revisada pela autora e aprovada para implementação

#### Implementação (concluída em 2026-06-05)
- [x] `src/memory/semantic.py` reescrito conforme contrato SPEC-MEM §4.3 (ChromaDB `user_facts`, sem relations/keywords)
- [x] `src/memory/episodic.py` refatorado conforme contrato SPEC-MEM §4.2 (ChromaDB + SQLite com atomicidade)
- [x] `src/config.py` e `.env.example` atualizados (USER_ID, SESSION_ID, EPISODIC_METADATA_DB)
- [x] `src/memory/__init__.py` exports atualizados
- [x] `src/utils/session.py` resolve `SESSION_ID` do .env ou gera UUID v4
- [x] Testes da §8 implementados e passando (`tests/test_spec_003_2.py`, 17 testes)
- [x] Nota de superseded adicionada à SPEC-003-1
- [x] Suite completa verde (36 testes, excluindo Ollama)

**Achado de implementação (2026-06-05):** o primeiro draft tinha o filtro
temporal aplicado no ChromaDB (`timestamp_unix` na metadata). Os testes
mostraram que isso é frágil — qualquer drift de timestamp entre Chroma e
SQLite invalida o filtro. A spec §3.2 já dizia "filtros temporais via SQLite";
ajustei a implementação para fazer **duas consultas** (SQLite p/ janela
temporal + Chroma p/ semântico) e intersectar em memória. Mais fiel ao
contrato e mais robusto.

---

### 11. Estimativa de Esforço

| Fase | Estimativa |
|---|---|
| Reescrita `semantic.py` | 1.5h |
| Refatoração `episodic.py` (ChromaDB + atomicidade) | 2.5h |
| Atualização config + .env | 0.5h |
| Reescrita de testes existentes | 1h |
| Novos testes (§8) | 1.5h |
| Smoke test + ajustes | 1h |
| **Total** | **~8h** |

---

### 12. Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Atomicidade Episodic falha em produção (drift entre stores) | Média | Adicionar job de verificação periódica como follow-up (SPEC-008 ou pós-MVP) |
| Performance de embedding em `add_conversation` impacta latência do turno | Média | Medir; se crítico, mover escrita para fila assíncrona (fora do escopo 003-2) |
| Custo de armazenamento ChromaDB cresce indefinidamente | Baixa | `cleanup()` com retention de 90d resolve para Episodic; Semantic não expira por design |
| Configuração `USER_ID` via env limita testes multi-usuário | Baixa | Aceitável no MVP single-user; expor override programático nos testes |

---

### 13. Dependências e Sequência

**Esta spec é pré-requisito de:**
- **SPEC-004** (RAG completo) — usa o mesmo `PersistentClient` ChromaDB definido aqui.
- **SPEC-007** (Agente 3) — consome a API refinada de `SemanticMemory` e `EpisodicMemory`.
- **SPEC-008** (Orquestrador) — usa `USER_ID`/`SESSION_ID` definidos aqui.

**Esta spec depende de:**
- **SPEC-MEM** (contratos canônicos).

**Atividade subsequente recomendada:** SPEC-004 (RAG completo com 3 domínios).
