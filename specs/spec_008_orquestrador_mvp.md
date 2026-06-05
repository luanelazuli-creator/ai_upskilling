# Engenharia de Especificação: SPEC-008
## Orquestrador MVP — Pipeline Triagem → Retrieval → ContextBundle → Síntese

**ID da Atividade:** TASK-008
**Data de Criação:** 05 de Junho de 2026
**Status:** 🟡 Em Refinamento
**Autor:** Desenvolvedor Capstone
**Depende de:** SPEC-MEM, SPEC-003-2, SPEC-004, SPEC-005, SPEC-006
**Consumido por:** SPEC-009 (Evals)

---

### 1. Visão Geral e Escopo

O **Orquestrador** é o coordenador único de cada turno de conversa. Recebe a mensagem do usuário e executa um pipeline determinístico:

```
query → triagem → retrieval (RAG + memórias) → ContextBundle → síntese → persistência (stub)
```

**Princípio fundamental:** *agentes são stateless; o orquestrador é dono do estado da sessão e da composição do contexto.* Isso preserva a separação definida em SPEC-MEM §1.

#### Em escopo (MVP)

- Sessão única por processo (1 REPL = 1 `session_id`); `WorkingMemory` viva como atributo da instância.
- Implementação concreta de `WorkingMemory` conforme contrato de SPEC-MEM §4.1.
- Implementação de `ContextBuilder` conforme contrato de SPEC-MEM §4.4 com orçamento de tokens §5.2.
- Despacho da `TriageOutput` (discriminated union de SPEC-005 §3): `TriageResult` segue o pipeline; `ClarificationNeeded` é entregue direto ao usuário como resposta do turno.
- Retrieval multi-fonte: RAG (uma ou várias coleções), Episodic recente, Semantic relevante, conforme `target_rag_collections` e `target_memory_tiers` da triagem.
- Top-K fixo por fonte + truncamento por orçamento de tokens (estratégia "fixa e simples").
- Política best-effort: falha de uma fonte não derruba o turno; warnings emitidos via OTel.
- Stub do Agente 3 para escrita em `EpisodicMemory` com sanitização de PII (Guardrails) ao final de cada turno.
- CLI REPL (`chat.py`) para smoke testing manual + função pura `Orchestrator.handle_turn()` para testes automatizados.
- Resposta tipada via `OrchestratorResponse` (união discriminada) para o consumidor (CLI hoje, Streamlit/API depois).

#### Fora de escopo

- **Multi-turno com clarification loop:** `ClarificationNeeded` é entregue ao usuário; a próxima query é re-roteada como nova (sem injetar `<previous_unclear_query>`). Decisão consciente para enxugar o MVP — SPEC-008.next pode adicionar.
- **Múltiplas sessões paralelas / persistência de sessão em disco:** registry in-memory + snapshot em arquivo ficam para fase futura.
- **Extração de fatos para Semantic Memory:** responsabilidade integral da SPEC-007 (Agente 3 real). Stub MVP só persiste em Episodic.
- **Multi-usuário:** `user_id` é fixo via `.env` (default `"luane"`) — single-user no MVP.
- **Re-rank cross-source:** scores não são normalizados entre coleções RAG / Episodic / Semantic. SPEC-009 mede e SPEC-008.next decide.
- **Streaming de tokens** (alinhado com SPEC-006).
- **UI gráfica** (Streamlit/Gradio): nova task quando MVP estabilizar.

---

### 2. Fluxo do Turno (visão geral)

```
                ┌────────────────────────────────────────────────────┐
                │            Orchestrator.handle_turn(query)         │
                └────────────────────────────────────────────────────┘
                                       │
            ┌──────────────────────────┼──────────────────────────┐
            ▼                          ▼                          ▼
   1. WM.add(query)          2. TriageAgent.triage(query)    (pré-pipeline)
                                       │
                          ┌────────────┴────────────┐
                          ▼                         ▼
              kind=clarification_needed     kind=triage_result
                          │                         │
                          │                         ▼
                          │           ┌─────────────────────────────┐
                          │           │  3. intent == "meta"?       │
                          │           │     sim → resposta direta   │
                          │           │     não → segue retrieval   │
                          │           └─────────────────────────────┘
                          │                         │
                          │                         ▼
                          │           4. Retrieval (RAG + Episodic + Semantic)
                          │                         │
                          │                         ▼
                          │           5. ContextBuilder.build()
                          │                         │
                          │                         ▼
                          │           6. SynthesisAgent.synthesize(query, bundle)
                          │                         │
                          ▼                         ▼
                ClarificationResponse        AnswerResponse
                          │                         │
                          └────────────┬────────────┘
                                       ▼
                          7. WM.add(resposta) — pós-pipeline
                                       │
                                       ▼
                          8. agent3_stub.persist_turn()
                             (sanitize → EpisodicMemory.add)
                                       │
                                       ▼
                          9. retorna OrchestratorResponse
```

---

### 3. Estado da Sessão

#### 3.1 `SessionState`

```python
@dataclass
class SessionState:
    session_id: str             # uuid gerado na inicialização do Orchestrator
    user_id: str                # fixo via settings (single-user MVP)
    started_at: datetime
    turn_count: int = 0
    working_memory: WorkingMemory  # ver §4
    last_intent: Optional[str] = None  # observabilidade
```

- Uma instância de `Orchestrator` carrega exatamente um `SessionState`.
- `turn_count` incrementa em cada `handle_turn` bem-sucedido (inclui clarification).
- `session_id` viaja em todos os spans OTel.

#### 3.2 Multi-turno

O orquestrador não mantém estado de clarification entre turnos (decisão MVP). Working Memory é o único canal de continuidade dentro da sessão:

- Turno N grava na WM: pergunta, intent, resposta.
- Turno N+1 lê a WM para compor `ContextBundle.working`.
- Trabalho exemplo: "voltando ao que falamos sobre X" recupera via `recent_episodic` (passada para SPEC-007) + `working`.

---

### 4. Working Memory (implementação concreta)

Cumpre o contrato de SPEC-MEM §4.1. Esta spec é a primeira a criá-la.

#### 4.1 Schema

```python
@dataclass
class WorkingItem:
    content: str
    importance: float           # 0.0 — 1.0
    source: Literal["user", "agent", "router", "system"]
    timestamp: datetime
    contains_pii: bool = False  # flag, não bloqueia
```

#### 4.2 Classe

```python
class WorkingMemory:
    def __init__(self, capacity: int = 10):
        self._items: list[WorkingItem] = []
        self._capacity = capacity

    def add(self, content: str, importance: float, source: str, contains_pii: bool = False) -> None
    def get_top_k(self, k: int = 10) -> list[WorkingItem]
    def clear(self) -> None
    def to_context_block(self) -> str   # formata para injeção em prompt
```

#### 4.3 Política de evicção

Quando `len(_items) > capacity`:
1. Ordena `(importance ASC, timestamp ASC)`.
2. Remove o primeiro (menos importante e mais antigo).
3. Repete até caber.

Default `capacity=10`, configurável via `WORKING_MEMORY_CAPACITY` no `.env`.

#### 4.4 Conteúdo gravado por turno (orquestrador)

| Evento | Conteúdo | Importance | Source |
|---|---|---|---|
| Início do turno | `query` do usuário | 1.0 | `user` |
| Após triagem (se kind=triage_result) | `f"intent={intent}"` | 0.8 | `router` |
| Após triagem (se janela temporal) | `f"janela={expression}"` | 0.7 | `router` |
| Fim do turno (se kind=answer) | `answer` truncado a 500 chars | 0.9 | `agent` |
| Fim do turno (se kind=clarification) | `f"clarif: {question}"` | 0.8 | `system` |

#### 4.5 Flag de PII

`WorkingMemory.add(contains_pii=True)` é setado pelo orquestrador via `Guardrails.has_pii()` antes da escrita. Não bloqueia (WM é efêmero, SPEC-MEM §6.1), mas viabiliza auditoria.

---

### 5. Pipeline Detalhado

#### 5.1 Fase 1 — Pré-pipeline

```python
self.session.turn_count += 1
contains_pii = Guardrails.has_pii(query)
self.session.working_memory.add(query, importance=1.0, source="user", contains_pii=contains_pii)
```

#### 5.2 Fase 2 — Triagem

```python
triage_output = await self.triage_agent.triage(query, clarification_round=0)
```

- `clarification_round=0` é constante no MVP (sem loop).
- Erros de triagem (timeout, JSON inválido) são capturados pelo wrapper de degradação (§9). Em último caso, retorna `OrchestratorResponse.error`.

#### 5.3 Fase 3 — Despacho por `kind`

```python
if triage_output.kind == "clarification_needed":
    self.session.working_memory.add(
        content=f"clarif: {triage_output.question}",
        importance=0.8, source="system",
    )
    await self._persist_turn_stub(query, triage_output.question)
    return ClarificationResponse(triage=triage_output)

# kind == "triage_result"
self.session.last_intent = triage_output.intent
self.session.working_memory.add(
    content=f"intent={triage_output.intent}",
    importance=0.8, source="router",
)
if triage_output.temporal_filter is not None:
    self.session.working_memory.add(
        content=f"janela={triage_output.temporal_filter.expression}",
        importance=0.7, source="router",
    )

if triage_output.intent == "meta":
    return self._handle_meta_intent(triage_output)
```

#### 5.4 Fase 4 — Retrieval (multi-fonte)

A partir de `target_rag_collections` e `target_memory_tiers`:

```python
rag_results = []
for collection in triage_output.target_rag_collections:
    try:
        chunks = await self.rag.search(
            collection=collection,
            query=query,
            top_k=settings.rag_top_k_per_collection,   # default 5
            temporal_filter=triage_output.temporal_filter,
            structured_filters=triage_output.structured_filters,
        )
        rag_results.extend(chunks)
    except Exception as e:
        emit_otel_warning("orchestrator.retrieval.rag_collection_failed",
                          collection=collection, error=str(e))
        # best-effort: segue com as outras coleções

episodic_results = []
if "episodic_recent" in triage_output.target_memory_tiers:
    episodic_results.extend(
        self.episodic.get_recent(user_id=self.session.user_id, n=settings.episodic_recent_n)  # default 3
    )
if "episodic_semantic" in triage_output.target_memory_tiers:
    episodic_results.extend(
        self.episodic.search_semantic(
            user_id=self.session.user_id, query=query,
            top_k=settings.episodic_semantic_top_k,    # default 3
            time_window=_to_tuple(triage_output.temporal_filter),
        )
    )

semantic_results = []
if "semantic" in triage_output.target_memory_tiers:
    semantic_results = self.semantic.search(
        user_id=self.session.user_id, query=query,
        top_k=settings.semantic_top_k,                  # default 5
    )
```

**Cross-domain:** se `target_rag_collections == ["diario", "referencias"]`, o loop simplesmente consulta as duas; cada uma devolve até `top_k`. O orçamento de tokens corta na próxima fase. **Sem re-rank cross-source** no MVP.

#### 5.5 Fase 5 — Montagem do `ContextBundle` (orçamento de tokens)

```python
bundle = self.context_builder.build(
    query=query,
    triage=triage_output,
    working=self.session.working_memory.get_top_k(),
    recent_episodic=episodic_results,
    semantic_facts=semantic_results,
    rag_chunks=rag_results,
    token_budget=settings.max_context_tokens,           # default 4096
)
```

##### 5.5.1 Algoritmo de truncamento

1. **Conta tokens** com heurística simples: `tokens ≈ len(text) // 4` (PT-BR; alinhado com tokenização BPE comum). Aceita imprecisão de ±15% no MVP.
2. **Aloca por seção** segundo SPEC-MEM §5.2:
   - Working: 10%, Episodic: 20%, Semantic: 20%, RAG: 40%, Reserva: 10%.
3. **Em cada seção**, ordena por relevance_score desc (ou timestamp desc para Working/Episodic) e adiciona até estourar o orçamento da seção. Se estourar, drop o item de menor score.
4. **Reaproveitamento de sobra:** se Working consumir < 10%, a sobra entra no orçamento de RAG (fonte mais "autoritativa"). Episódico e Semantic não cedem para RAG (preserva personalização).
5. **Emite OTel:** atributos `tokens_per_section`, `dropped_per_section`.

##### 5.5.2 Estrutura entregue ao Agente 2

Exatamente conforme SPEC-MEM §5.3 e SPEC-006 §2:

```python
ContextBundle(
    working=[...],
    recent_episodic=[...],
    semantic_facts=[...],
    rag_chunks=[...],
    metadata={
        "intent": triage_output.intent,
        "temporal_filter": triage_output.temporal_filter,
        "tokens_estimated": <int>,
        "retrieved_at": datetime.utcnow().isoformat(),
        "session_id": self.session.session_id,
        "turn": self.session.turn_count,
    },
)
```

#### 5.6 Fase 6 — Síntese

```python
synthesis_output = await self.synthesis_agent.synthesize(query=query, bundle=bundle)
# synthesis_output : SynthesisResult | NoEvidence
```

Resposta sempre encapsulada em `AnswerResponse` (orquestrador não filtra `NoEvidence` — entrega como resposta legítima, conforme decisão §1).

#### 5.7 Fase 7 — Pós-pipeline

```python
# 1. Atualiza Working Memory
display_text = synthesis_output.answer if synthesis_output.kind == "synthesis_result" \
               else synthesis_output.suggestion
self.session.working_memory.add(
    content=display_text[:500],
    importance=0.9, source="agent",
    contains_pii=Guardrails.has_pii(display_text),
)

# 2. Stub do Agente 3: persiste turno em Episodic com PII sanitization
await self._persist_turn_stub(user_message=query, agent_response=display_text)

return AnswerResponse(synthesis=synthesis_output)
```

---

### 6. Tratamento de Intents Especiais

#### 6.1 `intent == "meta"`

SPEC-005 §2 define: "Sem busca; resposta direta". O orquestrador responde com mensagem fixa, **sem chamar Agente 2**:

```python
def _handle_meta_intent(self, triage: TriageResult) -> MetaResponse:
    msg = (
        "Sou seu Second Brain. Posso ajudar com seu diário pessoal, "
        "progresso de cursos e referências (manuais, stakeholders, glossário). "
        "Faça uma pergunta sobre essas fontes."
    )
    self.session.working_memory.add(content=msg[:500], importance=0.9, source="agent")
    # Persiste turno como qualquer outro
    asyncio.create_task(self._persist_turn_stub(self.session.working_memory._items[0].content, msg))
    return MetaResponse(message=msg)
```

Mensagem template configurável via `META_INTENT_RESPONSE` no `.env` (permite ajuste sem deploy de código).

#### 6.2 `intent == "cross_domain"`

Sem caminho especial: o loop de retrieval (§5.4) já trata múltiplas coleções. Único cuidado: `temporal_filter` aplica-se às coleções que aceitam (RAG `diario`), ignorada nas outras.

---

### 7. Stub do Agente 3 (Persistência MVP)

Implementação enxuta para destravar continuidade end-to-end antes de SPEC-007.

#### 7.1 Contrato

```python
# src/agents/agent3_stub.py

async def persist_turn_stub(
    user_id: str,
    session_id: str,
    user_message: str,
    agent_response: str,
    intent: Optional[str],
    episodic_memory: EpisodicMemory,
) -> Optional[ConversationId]:
    """
    Sanitiza PII e grava em EpisodicMemory. NÃO extrai fatos para SemanticMemory
    (responsabilidade da SPEC-007 real).
    """
    try:
        clean_user = Guardrails.sanitize(user_message)
        clean_agent = Guardrails.sanitize(agent_response)
        return episodic_memory.add_conversation(
            user_id=user_id,
            session_id=session_id,
            user_message=clean_user,
            agent_response=clean_agent,
            intent=intent,
            pii_sanitized=True,
        )
    except Exception as e:
        emit_otel_error("orchestrator.persist_turn_stub.failed", error=str(e))
        return None  # best-effort: não derruba o turno
```

#### 7.2 Substituição futura

Quando SPEC-007 for implementada:
- Substituir a importação: `from src.agents.agent3 import persist_turn` (mesmo signature).
- Apagar `agent3_stub.py`.
- SPEC-007 adiciona extração de fatos para `SemanticMemory` no mesmo pipeline.

#### 7.3 Invariantes mantidos

- Toda escrita em Episodic carrega `pii_sanitized=True` (SPEC-MEM §6.2).
- Span OTel `orchestrator.persist_turn_stub` com atributos `success: bool`, `pii_types_found: list[str]` (vindos do Guardrails).

---

### 8. Contrato de Saída — `OrchestratorResponse`

União discriminada para o consumidor (CLI hoje, UI/API depois).

```python
from pydantic import BaseModel
from typing import Literal, Union
from src.agents.triage.schemas import ClarificationNeeded
from src.agents.synthesis.schemas import SynthesisOutput

class AnswerResponse(BaseModel):
    kind: Literal["answer"] = "answer"
    synthesis: SynthesisOutput     # SynthesisResult | NoEvidence (discriminada)
    session_id: str
    turn: int
    elapsed_ms: int

class ClarificationResponse(BaseModel):
    kind: Literal["clarification"] = "clarification"
    triage: ClarificationNeeded
    session_id: str
    turn: int
    elapsed_ms: int

class MetaResponse(BaseModel):
    kind: Literal["meta"] = "meta"
    message: str
    session_id: str
    turn: int
    elapsed_ms: int

class ErrorResponse(BaseModel):
    kind: Literal["error"] = "error"
    stage: Literal["triage", "retrieval", "context", "synthesis", "persist", "unknown"]
    message: str                   # mensagem amigável para o usuário
    session_id: str
    turn: int

OrchestratorResponse = Union[
    AnswerResponse, ClarificationResponse, MetaResponse, ErrorResponse
]
```

**Convenção:** `elapsed_ms` é tempo wall-clock do `handle_turn` completo. Útil para evals e debug.

---

### 9. Política de Degradação (Best-Effort com Avisos)

Conforme decisão de design (escolha "best-effort com avisos"), o orquestrador **prefere entregar resposta parcial a falhar**.

| Falha | Comportamento | OTel |
|---|---|---|
| Triagem timeout | Fallback amplo: `TriageResult` sintética com `intent="cross_domain"`, todas as coleções RAG, `confidence=0.0`, `classification_method="fallback"`. Pipeline segue. | `orchestrator.triage.timeout_fallback` |
| Triagem retorna JSON inválido após retry | Mesma fallback amplo. | `orchestrator.triage.invalid_output_fallback` |
| 1 coleção RAG falha | Continua com as outras. Bundle marca `metadata["failed_collections"]`. | `orchestrator.retrieval.rag_collection_failed` |
| Todas as coleções RAG falham | Bundle só com Episodic+Semantic; Agente 2 provavelmente retorna `NoEvidence(low_relevance)`. | `orchestrator.retrieval.all_rag_failed` |
| Episodic ou Semantic falham | Continua sem eles. | `orchestrator.retrieval.<tier>_failed` |
| Síntese timeout | Retorna `AnswerResponse(synthesis=NoEvidence(reason="off_topic", suggestion="LLM indisponível"))`. | `orchestrator.synthesis.timeout` |
| Stub do Agente 3 falha | Resposta é entregue ao usuário; só registra warning. **Não derruba o turno.** | `orchestrator.persist_turn_stub.failed` |
| Exceção inesperada não capturada | `ErrorResponse(stage=<phase>)` com mensagem "Algo deu errado no estágio X; tente novamente." | `orchestrator.handle_turn.unhandled` |

**Princípio:** todo `except` registra atributo OTel; nenhum silencia em silêncio.

---

### 10. CLI REPL (`chat.py`)

Smoke testing manual. Renderiza `OrchestratorResponse` em texto monoespaçado.

#### 10.1 Esqueleto

```python
# chat.py
async def main():
    orch = Orchestrator.from_settings(settings)
    print(f"Sessão {orch.session.session_id[:8]} iniciada. Ctrl+C para sair.\n")
    while True:
        try:
            query = input("você > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\ntchau.")
            break
        if not query:
            continue
        response = await orch.handle_turn(query)
        _render(response)

def _render(r: OrchestratorResponse) -> None:
    if r.kind == "answer":
        if r.synthesis.kind == "synthesis_result":
            print(f"\n[turno {r.turn}] {r.synthesis.answer}")
            for c in r.synthesis.citations:
                print(f"  └ [{c.chunk_id}] {c.source_file} (score {c.relevance_score:.2f})")
            print(f"  (confidence={r.synthesis.confidence:.2f}, {r.elapsed_ms}ms)\n")
        else:  # no_evidence
            print(f"\n[turno {r.turn}] {r.synthesis.suggestion}")
            print(f"  (motivo: {r.synthesis.reason}, {r.elapsed_ms}ms)\n")
    elif r.kind == "clarification":
        print(f"\n[turno {r.turn}] {r.triage.question}")
        if r.triage.detected_options:
            for opt in r.triage.detected_options:
                print(f"  • {opt}")
        print()
    elif r.kind == "meta":
        print(f"\n[turno {r.turn}] {r.message}\n")
    elif r.kind == "error":
        print(f"\n[erro/{r.stage}] {r.message}\n")
```

#### 10.2 Slash-commands mínimos

| Comando | Efeito |
|---|---|
| `/wm` | Imprime estado atual da Working Memory (para debug) |
| `/session` | Imprime `session_id`, `turn_count`, `last_intent` |
| `/clear` | Reseta Working Memory (mantém sessão) |
| `/quit` | Sai |

Sem framework de slash-commands sofisticado: `if query.startswith("/")` direto.

---

### 11. Modelo LLM

O orquestrador **não invoca LLM próprio**. Reusa:

- `OLLAMA_TRIAGE_MODEL` (SPEC-005 §7.1) — chamado por `TriageAgent`.
- `OLLAMA_SYNTHESIS_MODEL` (SPEC-006 §7) — chamado por `SynthesisAgent`.

Nada para configurar aqui exceto:

```bash
# .env (adições desta spec)
SESSION_USER_ID=luane                       # single-user MVP
MAX_CONTEXT_TOKENS=4096                     # orçamento total para o bundle
WORKING_MEMORY_CAPACITY=10                  # tier 1 (SPEC-MEM §4.1)
RAG_TOP_K_PER_COLLECTION=5
EPISODIC_RECENT_N=3
EPISODIC_SEMANTIC_TOP_K=3
SEMANTIC_TOP_K=5
META_INTENT_RESPONSE="Sou seu Second Brain..."
ORCHESTRATOR_TURN_TIMEOUT_S=60              # ceil global; aborta turno e devolve ErrorResponse
```

---

### 12. Instrumentação OTel

```
span: orchestrator.handle_turn
├── attributes: session_id, turn, user_id, query_length, response_kind, elapsed_ms
├── span: agent1.triage                 (já instrumentado por SPEC-005)
├── span: orchestrator.retrieval
│   ├── attributes: rag_collections_attempted, rag_chunks_collected,
│   │               episodic_records_collected, semantic_facts_collected,
│   │               failed_collections (list)
│   ├── span: orchestrator.retrieval.rag           (1 por coleção)
│   ├── span: orchestrator.retrieval.episodic
│   └── span: orchestrator.retrieval.semantic
├── span: orchestrator.build_context
│   ├── attributes: tokens_estimated, tokens_per_section (dict),
│   │               dropped_per_section (dict), bundle_size
├── span: agent2.synthesize             (já instrumentado por SPEC-006)
└── span: orchestrator.persist_turn_stub
    ├── attributes: success, pii_types_found, conversation_id
```

Consumido por SPEC-009 para:
- **Tempo total por turno** (p50/p95) — alvo MVP: p95 < 8s.
- **% de turnos com fallback** (triagem ampla, falha de coleção, etc.) — alvo: ≤ 10%.
- **% de turnos com erro** — alvo: ≤ 2%.
- **Token usage real vs orçamento** — calibração de `MAX_CONTEXT_TOKENS`.
- **Distribuição de `response_kind`** (answer / clarification / meta / error).

---

### 13. Arquivos Impactados

| Arquivo | Operação | Notas |
|---|---|---|
| `src/orchestrator/__init__.py` | **Criar** | exports |
| `src/orchestrator/orchestrator.py` | **Criar** | `Orchestrator` + `SessionState` |
| `src/orchestrator/context_builder.py` | **Criar** | `ContextBuilder` (§5.5) |
| `src/orchestrator/schemas.py` | **Criar** | `OrchestratorResponse` (§8) |
| `src/orchestrator/degradation.py` | **Criar** | wrappers de fallback (§9) |
| `src/memory/working.py` | **Criar** | `WorkingMemory` (§4) |
| `src/agents/agent3_stub.py` | **Criar** | stub MVP (§7) |
| `chat.py` | **Criar** | REPL (§10) |
| `src/config.py` | Adicionar settings | §11 |
| `.env.example` | Adicionar variáveis | §11 |
| `tests/test_spec_008.py` | **Criar** | cobertura §14 |
| `tests/test_working_memory.py` | **Criar** | cobertura específica do tier 1 |
| `tests/fixtures/orchestrator_scenarios.py` | **Criar** | cenários end-to-end mockados |

---

### 14. Plano de Testes

Testes operam com **mocks dos agentes** (TriageAgent, SynthesisAgent) e **fakes** das memórias (in-memory dicts). Smoke tests com Ollama real são marcados `@pytest.mark.ollama`.

#### 14.1 Working Memory (`test_working_memory.py`)

- `test_add_below_capacity_keeps_all`
- `test_add_above_capacity_evicts_lowest_importance_oldest`
- `test_get_top_k_orders_by_importance_then_timestamp`
- `test_to_context_block_serialization_format`
- `test_clear_empties_state`
- `test_capacity_configurable_via_settings`
- `test_pii_flag_preserved_round_trip`

#### 14.2 Context Builder

- `test_budget_split_matches_spec_mem_percentages`
- `test_working_overflow_drops_lowest_importance`
- `test_rag_overflow_drops_lowest_score`
- `test_working_underuse_yields_extra_to_rag`
- `test_empty_sources_produce_minimal_bundle`
- `test_metadata_carries_intent_and_session_id`

#### 14.3 Despacho do Orquestrador (com mocks)

- `test_handle_turn_triage_result_goes_through_full_pipeline`
- `test_handle_turn_clarification_returns_immediately`
- `test_handle_turn_meta_intent_returns_canned_message_without_synthesis`
- `test_handle_turn_cross_domain_queries_multiple_rag_collections`
- `test_handle_turn_writes_query_and_response_to_working_memory`
- `test_handle_turn_calls_persist_turn_stub_at_end`
- `test_handle_turn_emits_session_id_and_turn_in_response`
- `test_turn_count_increments_per_turn`

#### 14.4 Degradação (§9)

- `test_triage_timeout_falls_back_to_broad_search`
- `test_single_rag_collection_failure_continues_with_others`
- `test_all_rag_failures_still_produces_bundle_with_memory`
- `test_synthesis_timeout_returns_no_evidence_answer`
- `test_persist_stub_failure_does_not_block_response`
- `test_unhandled_exception_returns_error_response`
- `test_every_failure_path_emits_otel_attribute`

#### 14.5 Stub do Agente 3

- `test_persist_turn_stub_sanitizes_pii_before_write`
- `test_persist_turn_stub_marks_pii_sanitized_true`
- `test_persist_turn_stub_returns_none_on_failure_no_raise`

#### 14.6 CLI REPL (smoke)

- `test_render_answer_response_includes_citations`
- `test_render_clarification_lists_options`
- `test_render_no_evidence_shows_suggestion`
- `test_slash_wm_prints_working_memory_state` (mock stdin/stdout)

#### 14.7 Integração end-to-end com Ollama (`@pytest.mark.ollama`)

- `test_real_pipeline_diary_query` — query "o que fiz dia 11" → resposta ancorada com citação.
- `test_real_pipeline_user_profile_query` — query "quais minhas preferências" → semantic_facts citados.
- `test_real_pipeline_unclear_query_clarifies` — "ok" → ClarificationResponse.
- `test_real_pipeline_meta_query_returns_canned` — "o que você sabe fazer" → MetaResponse.
- `test_real_pipeline_persists_to_episodic` — após N turnos, `EpisodicMemory.get_recent(N)` contém todos.

---

### 15. Política de Erro

| Cenário | Comportamento |
|---|---|
| `query` vazia / só whitespace | Retorna `ClarificationResponse` com `triage.reason="low_confidence"` direto (sem chamar agentes) |
| `Orchestrator` instanciado sem dependências | `ValueError` no constructor; falha rápido |
| `session_id` colide entre instâncias | Não acontece (UUID4); mas log warning se ID externo for fornecido e colidir |
| Timeout global do turno (`ORCHESTRATOR_TURN_TIMEOUT_S`) | Cancela tasks restantes; retorna `ErrorResponse(stage=<última fase>)` |
| Working Memory write falha (impossível em RAM, mas defensivo) | Log warning; continua |
| OTel exporter falha | Não derruba turno; OTel SDK já é fault-tolerant |

---

### 16. Checklist de Aceite

#### Pré-implementação
- [x] Pipeline em 7 fases definido (§2, §5)
- [x] `SessionState` e fluxo multi-turno simples documentados (§3)
- [x] `WorkingMemory` especificada com schema, API e política de evicção (§4)
- [x] Algoritmo de orçamento de tokens definido (§5.5.1)
- [x] Despacho por `kind` (triage_result, clarification, meta) explicitado (§5.3, §6)
- [x] Stub do Agente 3 com contrato substituível por SPEC-007 (§7)
- [x] `OrchestratorResponse` discriminada (§8)
- [x] Política de degradação best-effort tabulada (§9)
- [x] CLI REPL com renderer e slash-commands mínimos (§10)
- [x] Settings configuráveis catalogadas (§11)
- [x] Spans OTel mapeados (§12)
- [x] Plano de testes com mocks + smoke com Ollama (§14)
- [ ] Spec revisada e aprovada para implementação

#### Implementação (futura)
- [ ] `src/orchestrator/` criado conforme §13
- [ ] `WorkingMemory` com testes verdes
- [ ] `ContextBuilder` cobrindo as 5 etapas do §5.5.1
- [ ] `Orchestrator.handle_turn()` cobrindo as 7 fases
- [ ] Stub do Agente 3 invocado ao fim de cada turno
- [ ] `chat.py` REPL funcional
- [ ] Mocks + fakes prontos em `tests/fixtures/orchestrator_scenarios.py`
- [ ] Smoke end-to-end com Ollama passa para 5 queries variadas
- [ ] Latência p95 < 8s em hardware da Luane
- [ ] Distribuição de `response_kind` registrada em OTel para uso por SPEC-009

---

### 17. Estimativa de Esforço

| Fase | Estimativa |
|---|---|
| `WorkingMemory` (classe + testes) | 1.5h |
| `ContextBuilder` (orçamento de tokens + truncamento) | 2.5h |
| `Orchestrator.handle_turn` esqueleto (fases 1–3, 6–7) | 2h |
| Retrieval multi-fonte + best-effort wrappers | 2.5h |
| Tratamento de `meta` e cross_domain | 1h |
| Stub do Agente 3 | 1h |
| `OrchestratorResponse` schemas + renderer da CLI | 1.5h |
| CLI REPL + slash-commands | 1.5h |
| Instrumentação OTel completa | 1.5h |
| Mocks/fakes e testes unitários | 3h |
| Smoke com Ollama + ajustes finos | 2h |
| **Total** | **~20h** |

---

### 18. Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Heurística de `tokens ≈ len/4` errar muito em PT-BR e causar overflow no Mistral | Média | Atributos OTel `tokens_estimated` vs `tokens_in` real (vinda de SPEC-006); calibra divisor em ajuste rápido. Fallback opcional: integrar `tiktoken` numa task posterior. |
| Ausência de clarification loop causa loops infinitos com usuário re-perguntando vago | Baixa | Mensagem da `ClarificationNeeded` já lista opções (SPEC-005 §6); UX MVP aceitável. SPEC-008.next pode introduzir loop. |
| Stub do Agente 3 escreve algo que SPEC-007 vai precisar reescrever | Baixa | Contrato do stub é idêntico ao do Agente 3 real (mesma signature); SPEC-007 só troca implementação. Testes do Episodic continuam válidos. |
| Best-effort esconde bugs reais (erros silenciosos parecem normais) | Média | Toda degradação emite atributo OTel próprio; eval SPEC-009 inclui métrica "% turnos com qualquer fallback". |
| Single-process session perde contexto se REPL crashar | Baixa (MVP) | Documentado em §1; persistência de sessão é roadmap. Para evals, sessões são curtas. |
| Cross-domain sem re-rank traz chunks irrelevantes da segunda coleção | Média | Top-K conservador (5/coleção) + orçamento corta os de score baixo. SPEC-009 mede e SPEC-008.next pode adicionar re-rank. |
| `meta` intent canned response fica datada | Baixa | Configurável via `.env`; sem deploy de código. |
| Concorrência de turnos no mesmo `session_id` (usuário aperta Enter 2x) | Baixa | `handle_turn` é async sequencial na CLI; REPL não dispara em paralelo. UI futura precisará lock. |

---

### 19. Dependências e Sequência

**Esta spec depende de:**
- **SPEC-MEM** — contratos de `ContextBundle`, tiers, política de PII, orçamento.
- **SPEC-003-2** — `EpisodicMemory.add_conversation`, `get_recent`, `search_semantic`, `SemanticMemory.search`.
- **SPEC-004** — `RAGRetriever.search(collection, query, top_k, temporal_filter, structured_filters)`.
- **SPEC-005** — `TriageAgent.triage()` retorna `TriageOutput`.
- **SPEC-006** — `SynthesisAgent.synthesize(query, bundle)` retorna `SynthesisOutput`.

**Esta spec é pré-requisito de:**
- **SPEC-007** (Agente 3 real) — substitui `agent3_stub` mantendo a signature.
- **SPEC-009** (Evals) — consome `OrchestratorResponse` + spans OTel para todas as métricas end-to-end.

**Atividade subsequente recomendada:** SPEC-009 (Evals) — após SPEC-008 há chat real testável; já é viável montar o dataset e medir Faithfulness, Personalization e Continuidade contra o baseline.

---

### 20. Decisões Registradas (Tradeoffs)

| Decisão | Alternativa rejeitada | Por quê |
|---|---|---|
| Sem clarification loop no MVP | Loop até 2 rodadas com estado entre turnos | Reduz superfície de bug; UX aceitável (usuário re-pergunta); cabe em SPEC-008.next |
| 1 processo = 1 sessão | Session registry in-memory ou persistente em disco | Single-user MVP; bug rate menor; persistência é overhead sem ganho mensurável |
| Top-K fixo + truncate por tokens | K adaptativo ou re-rank global | Previsibilidade > sofisticação no MVP; SPEC-009 decide se vale evoluir |
| Best-effort com avisos OTel | Fail-fast tipado ou circuit breaker | Local, single-user, sem dependências externas críticas — best-effort entrega valor; circuit breaker é overkill |
| Stub do Agente 3 em vez de pular escrita | Pular persistência até SPEC-007 | "Continuidade real" do Second Brain é demo crítico; stub destrava sem violar contratos |
| Heurística `len/4` para tokens | `tiktoken` desde o MVP | Mistral usa tokenizer próprio; tiktoken seria aproximação igual. Heurística simples evita dep + setup. |
| `meta` respondido pelo orquestrador (sem LLM) | Agente 2 com bundle vazio | Custo zero, latência zero; resposta determinística mais previsível |
| Cross-domain sem re-rank | Re-rank global de scores | Scores de fontes diferentes não são comparáveis sem normalização; complexidade alta no MVP |
| WorkingMemory implementada nesta spec | Spec separada (003-3) | Orquestrador é dono da sessão; coesão > separação artificial |

---

### 21. Próximas atividades geradas por esta spec

1. **SPEC-007** — Agente 3 real: extração de fatos para `SemanticMemory`, persistência avançada de Episodic, comandos "esqueça X" / "apague conversa de Y".
2. **SPEC-009** — Evals end-to-end consumindo `OrchestratorResponse` + spans.
3. **SPEC-008.next (roadmap)** — Clarification loop (até 2 rodadas), session registry, sessão persistente em disco, re-rank cross-source, integração `tiktoken`.
4. **Task de UI (roadmap)** — Streamlit/Gradio mínima alimentada por `Orchestrator.handle_turn()`.
