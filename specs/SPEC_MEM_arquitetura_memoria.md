# Engenharia de Especificação: SPEC-MEM
## Arquitetura de Memória (Transversal)

**ID da Atividade:** TASK-MEM (Transversal)
**Data de Criação:** 05 de Junho de 2026
**Status:** 🟡 Em Refinamento
**Autor:** Desenvolvedor Capstone
**Tipo:** Spec Transversal — define contratos consumidos por outras specs

---

### 0. Propósito e relação com outras specs

Esta spec **não implementa** nenhum agente. Ela define **contratos de memória** que serão consumidos por:

- **SPEC-003-2** (migração): refatora `SemanticMemory` e `EpisodicMemory` existentes para aderir a este contrato.
- **SPEC-004** (RAG): consome a fronteira definida aqui entre "RAG de documentos" e "Memória Semântica de usuário".
- **SPEC-005, 006, 007** (Agentes 1, 2, 3): cada agente consome um subconjunto dos tiers definidos aqui.
- **SPEC-008** (Orquestrador): centraliza a geração de contexto conforme política definida na §5.
- **SPEC-009** (Evals): consome métricas da §8.

**Supersede parcial:** A `MEMORY_ARCHITECTURE_SPECIFICATION.md` (referência teórica de 4 tiers com JSON+keyword) é reconciliada com a SPEC-003-1 (que já implementou busca vetorial). Esta SPEC-MEM é a fonte de verdade canônica daqui em diante.

---

### 1. Visão Geral

A arquitetura de memória do Second Brain é estratificada em **4 tiers** com responsabilidades, mecanismos de busca e políticas de persistência distintos. A separação reflete uma decisão consciente de **híbrido por tier** — cada tier usa a tecnologia adequada à sua dinâmica, não a mais sofisticada disponível.

#### Princípios norteadores

1. **Separação por dinâmica de dados**, não por tecnologia. Tiers com alto volume e busca semântica usam vetorial; tiers pequenos e estruturados usam JSON+keyword.
2. **RAG ≠ Memória Semântica.** RAG indexa documentos do usuário (arquivos em `/data`). Memória Semântica indexa fatos aprendidos sobre o usuário durante conversas. São coleções distintas, com origens distintas e ownership distinto.
3. **Orquestrador centraliza a montagem de contexto.** Agentes são consumidores, não montadores. Isso permite orçamento unificado de tokens e auditoria centralizada.
4. **PII é responsabilidade pré-escrita.** Sanitização acontece antes de qualquer persistência (Episodic, Semantic). Working memory pode conter PII (efêmero) mas é marcado.

---

### 2. Os 4 Tiers — Contrato e Fronteiras

#### 2.1 Working Memory (RAM, efêmera)

| Atributo | Valor |
|---|---|
| **Storage** | Lista in-memory (não persistente) |
| **Capacidade** | 10 itens (configurável via `working_memory_capacity`) |
| **Busca** | Ordenação por `(importance, timestamp)` desc |
| **Eviction** | Quando excede capacidade: remove item de menor `importance` e mais antigo |
| **Persistência** | Nenhuma; descartado ao fim da sessão |
| **Quem escreve** | Orquestrador (turno atual) + Agente 1 (intent/contexto temporal detectado) |
| **Quem lê** | Orquestrador (montagem de contexto) |

**Conteúdo típico:**
- Última pergunta do usuário (importance=1.0)
- Última resposta do agente (importance=0.9)
- Intent classificado pelo Agente 1 (importance=0.8)
- Janela temporal ativa detectada (ex: "usuário está perguntando sobre semana passada", importance=0.7)

**Por quê em RAM:** acessado a cada turno; persistência seria overhead sem benefício.

---

#### 2.2 Episodic Memory (histórico de conversas)

| Atributo | Valor |
|---|---|
| **Storage** | ChromaDB (vetorial) + SQLite (metadata estruturada) |
| **Coleção ChromaDB** | `episodic_conversations` |
| **Schema SQLite** | `(id, user_id, session_id, timestamp, intent, pii_sanitized: bool)` |
| **Busca** | Híbrida: semântica (ChromaDB) + filtros temporais/usuário (SQLite) |
| **Persistência** | Persistente; retenção configurável (default 90 dias) |
| **Quem escreve** | Agente 3 (após sanitização de PII) |
| **Quem lê** | Agente 1 (recência), Orquestrador (recall semântico para context generation) |

**Conteúdo:** par `(user_message, agent_response)` por turno, com metadata.

**Por quê híbrido:** queries do tipo "o que conversamos sobre X na semana passada" precisam de filtro temporal (SQLite) **e** match semântico em conteúdo (ChromaDB). Cada storage carrega o que faz melhor.

**Decisão de design:** o ChromaDB armazena o texto concatenado `user_message + " | " + agent_response` para embedding único por turno. Texto bruto vive lá; SQLite carrega só metadata indexável.

---

#### 2.3 Semantic Memory (fatos aprendidos sobre o usuário)

| Atributo | Valor |
|---|---|
| **Storage** | ChromaDB |
| **Coleção ChromaDB** | `user_facts` (separada do RAG) |
| **Busca** | Semântica vetorial |
| **Persistência** | Persistente; não expira (suporta deleção explícita) |
| **Quem escreve** | Agente 3 (extração de fatos a partir de conversas) |
| **Quem lê** | Orquestrador (personalização), Agente 1 (perfil do usuário), Agente 2 (contexto sobre preferências) |

**Conteúdo típico:**
- "Luane prefere respostas curtas e diretas"
- "Luane está fazendo o curso Data Engineer Certificate"
- "Luane usa Thoughtworks como empresa atual"
- "Stakeholder X é PM no projeto Y"

**⚠️ Fronteira crítica com RAG:**

| | RAG | Memória Semântica |
|---|---|---|
| **Origem do dado** | Arquivos em `/data` | Conversas com o usuário |
| **Coleções** | `diario`, `cursos`, `referencias` | `user_facts` |
| **Quem indexa** | Pipeline de ingestão (SPEC-004) | Agente 3 (runtime) |
| **Conteúdo** | Texto longo (chunks de documentos) | Fatos curtos atomicamente formulados |
| **Atualização** | Re-ingestão de arquivos | Extração contínua durante conversas |

**Regra de roteamento (consumida pelo Agente 1):**
- "O que escrevi no diário em 11/06?" → **RAG** (coleção `diario`)
- "Quais minhas preferências de comunicação?" → **Semantic** (coleção `user_facts`)
- "Quem é o stakeholder X?" → **RAG** (coleção `referencias`)
- "Qual era meu objetivo de carreira mês passado?" → **Episodic** (filtro temporal + semântica)

---

#### 2.4 Procedural Memory (ROADMAP — não implementar agora)

| Atributo | Valor |
|---|---|
| **Storage** | JSON + busca por keyword |
| **Path** | `./data/procedural_memory.json` |
| **Status** | **Contrato definido nesta spec; implementação fora do escopo do Capstone** |
| **Conteúdo planejado** | Golden Prompts como procedures reutilizáveis (ex: "fazer pesquisa acadêmica") |

**Por quê fora de escopo:** o projeto tem 7 specs pendentes para entregar valor mínimo (RAG + 3 agentes + evals). Procedural é melhoria pós-MVP.

**Decisão de design (para quando for implementado):**
- Source: arquivos em `data/cursos/Golden Prompts/`
- Schema: `{name, steps[], description, source_file, usage_count}`
- Busca: keyword simples (poucos itens, alta especificidade)
- Quem leria: Agente 2 (quando intent é "execute este tipo de tarefa")

---

### 3. Fronteira RAG vs Semantic Memory (resumo executivo)

Repetido aqui propositalmente porque é a decisão arquitetural mais importante desta spec.

```
┌─────────────────────────────────────────────────────────────┐
│                     ChromaDB (único)                         │
├──────────────────────┬──────────────────────────────────────┤
│        RAG           │       MEMORY                          │
│  (documentos)        │   (interações)                       │
├──────────────────────┼──────────────────────────────────────┤
│  • diario            │  • episodic_conversations            │
│  • cursos            │  • user_facts (= Semantic)           │
│  • referencias       │                                       │
├──────────────────────┼──────────────────────────────────────┤
│  Origem: arquivos    │  Origem: conversas runtime            │
│  Ownership: ingestão │  Ownership: Agente 3                  │
│  Spec: SPEC-004      │  Spec: SPEC-007                       │
└──────────────────────┴──────────────────────────────────────┘
```

Mesma stack (ChromaDB), coleções separadas, ownership separado, ciclo de vida separado.

---

### 4. Contratos de API

**Importante:** as assinaturas abaixo são **contratos**, não implementação. Tipos exatos (sync vs async, retorno) serão definidos nas specs de cada módulo.

#### 4.1 WorkingMemory

```python
class WorkingMemory:
    def add(content: str, importance: float, source: Literal["user","agent","router","system"]) -> None
    def get_top_k(k: int = 10) -> List[WorkingItem]
    def clear() -> None
    def to_context_block() -> str  # formatado para injeção em prompt
```

#### 4.2 EpisodicMemory

```python
class EpisodicMemory:
    def add_conversation(
        user_id: str,
        session_id: str,
        user_message: str,
        agent_response: str,
        intent: Optional[str],
        pii_sanitized: bool,
    ) -> ConversationId

    def search_semantic(
        user_id: str,
        query: str,
        top_k: int = 5,
        time_window: Optional[Tuple[datetime, datetime]] = None,
    ) -> List[ConversationRecord]

    def get_recent(user_id: str, n: int = 5) -> List[ConversationRecord]

    def cleanup(retention_days: int = 90) -> int  # retorna nº de registros removidos
```

#### 4.3 SemanticMemory (fatos do usuário)

```python
class SemanticMemory:
    def add_fact(
        user_id: str,
        content: str,
        category: Optional[str],  # ex: "preference", "profile", "context"
        source_conversation_id: Optional[ConversationId],
        confidence: float,
    ) -> FactId

    def search(user_id: str, query: str, top_k: int = 3) -> List[Fact]

    def delete_fact(fact_id: FactId) -> None  # direito do usuário

    def list_by_category(user_id: str, category: str) -> List[Fact]
```

#### 4.4 ContextBuilder (orquestrador)

```python
class ContextBuilder:
    def build_for_llm(
        user_id: str,
        session_id: str,
        current_message: str,
        token_budget: int,
    ) -> ContextBundle
```

`ContextBundle` é um objeto com seções nomeadas (working, recent_episodic, semantic, rag) — não uma string. A serialização para prompt fica no agente que consome.

---

### 5. Pipeline de Context Generation para LLM

O orquestrador é a **única entidade** que monta contexto consolidado. Cada agente declara via API o que precisa; o orquestrador atende dentro do orçamento de tokens.

#### 5.1 Ordem de prioridade (alta → baixa)

1. **Working Memory** (sessão atual; sempre incluída integralmente se couber)
2. **Episodic recente** (últimos N turnos; default N=3)
3. **Semantic relevante** (top-K fatos do usuário com match semântico; default K=5)
4. **RAG relevante** (top-K chunks dos documentos; default K=5)

#### 5.2 Orçamento de tokens (default)

| Seção | % do budget total |
|---|---|
| Working Memory | até 10% |
| Episodic recente | até 20% |
| Semantic | até 20% |
| RAG | até 40% |
| Reserva (instrução do agente + pergunta) | 10% |

Configurável por agente via `ContextBuilder.build_for_llm(..., budget_overrides=...)`.

#### 5.3 Estrutura do bundle entregue ao agente

```python
@dataclass
class ContextBundle:
    working: List[WorkingItem]
    recent_episodic: List[ConversationRecord]
    semantic_facts: List[Fact]
    rag_chunks: List[RAGChunk]
    metadata: Dict[str, Any]  # token counts, retrieved_at, etc
```

O agente decide como serializar isso em prompt. Permite que Agente 2 (síntese) e Agente 1 (triagem) formatem diferente.

---

### 6. Política de PII

#### 6.1 Pontos de sanitização

| Tier | Sanitização antes da escrita? | Quem executa |
|---|---|---|
| Working | Não (efêmero), mas flag `contains_pii` | Detector inline (Guardrails.has_pii) |
| Episodic | **Obrigatória** | Agente 3 (chama Guardrails.sanitize) |
| Semantic | **Obrigatória** | Agente 3 (chama Guardrails.sanitize) |
| RAG | Validação em ingestão (SPEC-004) | Pipeline de ingestão |

#### 6.2 Invariantes auditáveis

- Toda escrita em Episodic e Semantic carrega flag `pii_sanitized: bool` no metadata.
- Toda chamada de `sanitize()` gera um span OTel com atributos `pii_types_found: List[str]` e `count: int`.
- Eval de privacidade (SPEC-009) consulta esses spans para calcular taxa de vazamento.

---

### 7. Política de Retenção

| Tier | Política | Configurável via |
|---|---|---|
| Working | Descartado ao fim da sessão | N/A |
| Episodic | Deletar após N dias | `EPISODIC_RETENTION_DAYS` (default 90) |
| Semantic | Não expira; suporta deleção explícita do usuário | API `delete_fact()` |
| Procedural | N/A | N/A |
| RAG | Re-indexação em massa quando arquivos mudam | Pipeline de ingestão |

**Direito de esquecimento do usuário:**
- Comando explícito "esqueça X" → Agente 3 chama `SemanticMemory.delete_fact()` por busca semântica do que esquecer.
- Comando explícito "apague nossa conversa de Y" → Agente 3 chama `EpisodicMemory` com filtro temporal/conteúdo.

---

### 8. Métricas para SPEC-009 (Evals)

Esta seção define **o que será medido**, não como. SPEC-009 detalha o dataset e a infraestrutura de eval.

#### 8.1 Memory Recall

- **Episodic Recall@k**: dado um conjunto de queries com ground truth de qual conversa deveria ser recuperada, mede acerto no top-k.
- **Semantic Recall@k**: idem para fatos do usuário.
- **Latência de busca por tier** (p50, p95).

#### 8.2 Memory Faithfulness

- **Fact Extraction Faithfulness**: dado um par `(conversa, fato extraído)`, o fato é literalmente sustentado pela conversa? Mede alucinação de extração.
- **Context-Response Faithfulness**: dado um `(ContextBundle, resposta do agente)`, a resposta é sustentada pelo bundle? Mede alucinação de síntese.

#### 8.3 Privacy

- **PII Leak Rate**: %  de escritas em Episodic/Semantic que contêm PII detectável após sanitização. Alvo: **0%**.
- **PII Detection Recall**: % de PII presentes em entrada que foram detectados pelo Guardrails. Alvo: ≥ 95% para CPF, email, telefone.

#### 8.4 Comparativo Baseline

Conforme SPEC-001 §4: rodar os mesmos prompts em pipeline single-agent (sem tiers de memória, sem orquestrador) e medir delta em **Faithfulness**, **Personalization** (uso de Semantic) e **Continuidade** (uso de Episodic).

---

### 9. Decisões registradas e tradeoffs

| Decisão | Alternativa rejeitada | Por quê |
|---|---|---|
| Híbrido por tier (vetorial em Episodic+Semantic; JSON+keyword em Working+Procedural) | Tudo vetorial OU tudo JSON | Vetorial em Working é overkill; JSON em Semantic não escala |
| RAG e Semantic em coleções separadas | RAG é subsistema de Semantic | Ownership e ciclo de vida são distintos; juntar acopla ingestão a runtime |
| Orquestrador centraliza context generation | Cada agente monta o seu | Permite orçamento unificado de tokens e auditoria; agentes ficam stateless |
| Procedural Memory é roadmap, não MVP | Implementar agora | Escopo do Capstone tem 7 specs pendentes; valor marginal |
| Migração da SPEC-003-1 vira SPEC-003-2 separada | Reescrever 003-1 in-place | Preserva histórico das decisões |

---

### 10. Pré-requisitos e dependências

**Esta spec depende de:** SPEC-001 (arquitetura inicial), SPEC-003-1 (módulos existentes a migrar).

**Esta spec é pré-requisito de:** SPEC-003-2, SPEC-004, SPEC-005, SPEC-006, SPEC-007, SPEC-008, SPEC-009.

---

### 11. Checklist de aceite desta spec (não de implementação)

- [x] Os 4 tiers estão definidos com storage, busca, persistência e ownership
- [x] Fronteira RAG vs Semantic está explícita e exemplificada
- [x] Contratos de API estão declarados (assinaturas, não corpo)
- [x] Pipeline de context generation está definido com orçamento de tokens
- [x] Política de PII define pontos de sanitização e invariantes auditáveis
- [x] Política de retenção define ciclo de vida por tier
- [x] Métricas para evals estão listadas
- [x] Decisões e tradeoffs estão registrados
- [ ] Spec foi revisada pela autora e aprovada para virar pré-requisito das próximas

---

### 12. Próximas atividades geradas por esta spec

1. **SPEC-003-2** — Migração de `SemanticMemory` (JSON→ChromaDB) e `EpisodicMemory` (adicionar layer vetorial).
2. **SPEC-004** — RAG com 3 domínios indexados, consumindo a fronteira definida aqui.
3. **SPEC-007** — Agente 3 implementa os contratos das §4.2 e §4.3 + invariantes de PII da §6.
4. **SPEC-008** — Orquestrador implementa `ContextBuilder` da §4.4 e §5.
5. **SPEC-009** — Evals consomem métricas da §8.
