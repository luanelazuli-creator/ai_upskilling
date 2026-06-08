# Engenharia de Especificação: SPEC-006
## Agente 2 — Síntese e Resposta Ancorada

**ID da Atividade:** TASK-006
**Data de Criação:** 05 de Junho de 2026
**Status:** 🟡 Em Refinamento
**Autor:** Desenvolvedor Capstone
**Depende de:** SPEC-MEM, SPEC-003-2, SPEC-004
**Consumido por:** SPEC-008 (Orquestrador)

---

### 1. Visão Geral e Escopo

O **Agente 2 (Síntese)** transforma um `ContextBundle` pronto + uma query do usuário em uma **resposta tipada e ancorada em fontes**.

**Escopo enxuto:**
- **Só síntese.** Retrieval vive na SPEC-008 (orquestrador). Triagem vive na SPEC-005.
- **Stateless.** Não consulta nenhum store; trabalha apenas com o que recebe via parâmetros.
- **Ancorada.** Toda afirmação factual deve ser justificada por uma `citation` para um chunk do bundle.

**Princípio fundamental:** *o agente prefere dizer "não sei" a alucinar.* Quando o bundle não cobre a query, retorna `NoEvidence` em vez de inventar.

#### Em escopo
- Serialização de `ContextBundle` em prompt para LLM
- Geração de resposta com citações inline obrigatórias
- Detecção de "nada encontrado" (threshold de relevância)
- Validação pós-geração (faithfulness leve: citações batem com IDs do bundle)
- Integração via Pydantic AI

#### Fora de escopo
- Montar o `ContextBundle` (SPEC-008)
- Triagem ou roteamento (SPEC-005)
- Escrita em memória (SPEC-007)
- Streaming de tokens (pós-MVP)

---

### 2. Contrato de Entrada — `ContextBundle`

Recebe o `ContextBundle` definido em SPEC-MEM §5.3:

```python
@dataclass
class ContextBundle:
    working: list[WorkingItem]
    recent_episodic: list[ConversationRecord]
    semantic_facts: list[Fact]
    rag_chunks: list[RAGChunk]
    metadata: dict  # token counts, retrieved_at, intent (vindo da SPEC-005)
```

#### 2.1 Pré-condições garantidas pelo orquestrador

- `rag_chunks`, `semantic_facts` já foram **filtrados pelo `user_id`**.
- Cada `RAGChunk` carrega `id`, `content`, `collection`, `relevance_score`, `metadata` (com `source_file`).
- O orçamento de tokens já foi aplicado (orquestrador trunca antes de entregar).
- `metadata["intent"]` carrega o `intent` da SPEC-005 (ex.: `diary_lookup`).

#### 2.2 O que o agente faz com cada seção

| Seção | Uso |
|---|---|
| `rag_chunks` | Fonte primária; citações apontam para esses IDs |
| `semantic_facts` | Personalização (ex.: "responder de forma curta"); citáveis com prefixo `fact:` |
| `recent_episodic` | Continuidade de fio narrativo; não citável (não é "evidência factual") |
| `working` | Contexto da sessão atual; não citável |

---

### 3. Contrato de Saída (Pydantic, união discriminada)

```python
from pydantic import BaseModel, Field
from typing import Literal, Union

class Citation(BaseModel):
    chunk_id: str           # id do RAGChunk ou f"fact:{fact_id}" para SemanticFact
    source_file: str        # nome do arquivo (rastreável pelo usuário)
    collection: str         # diario | cursos | referencias | user_facts
    relevance_score: float

class SynthesisResult(BaseModel):
    kind: Literal["synthesis_result"] = "synthesis_result"
    answer: str             # texto livre com citações inline [chunk_id]
    citations: list[Citation]
    confidence: float = Field(ge=0.0, le=1.0)
    used_intent: str        # ecoado do bundle (auditoria)

class NoEvidence(BaseModel):
    kind: Literal["no_evidence"] = "no_evidence"
    reason: Literal[
        "empty_bundle",         # bundle veio vazio
        "low_relevance",        # nenhum chunk acima do threshold
        "off_topic",            # bundle existe mas LLM julgou não relacionado
    ]
    suggestion: str             # mensagem para o usuário (ex.: "tente especificar uma data")
    used_intent: str

SynthesisOutput = Union[SynthesisResult, NoEvidence]
```

**Discriminação:** o orquestrador despacha por `kind` sem `isinstance`.

---

### 4. Estratégia de Citação

#### 4.1 Formato inline

```
"Você terminou o módulo 4 do Data Engineer Certificate [chunk_de_001].
Sua preferência é receber respostas curtas [fact:f_42]."
```

- IDs entre colchetes apontam para `chunk_id` de algum elemento do bundle.
- Prefixo `fact:` distingue fatos da Semantic Memory de chunks do RAG.
- Múltiplas citações em sequência: `[id_1][id_2]` (sem vírgula).

#### 4.2 Lista `citations[]` no output

Para cada `chunk_id` citado inline, deve haver um objeto `Citation` correspondente em `citations[]` com os metadados completos. Isso permite:
- Renderização rica na UI (clique no `[id_1]` mostra o trecho).
- Auditoria automatizada (SPEC-009 mede se a citação realmente sustenta a afirmação).
- Detecção de alucinação: citação para ID inexistente é erro.

#### 4.3 Política de citação obrigatória

Toda afirmação que derive do bundle **deve** ter citação. Saudações, instruções genéricas e perguntas de clarificação não precisam.

**Heurística de detecção (validador, §8):**
- Se `answer` contém mais de 30 palavras E `citations` está vazia → soft warning + `confidence *= 0.5`.
- Se algum `[id]` inline aponta para ID fora do bundle → erro hard; retorna `NoEvidence(reason="off_topic")`.

---

### 5. Política "Nada Encontrado" — `NoEvidence`

O agente retorna `NoEvidence` em três condições:

| `reason` | Condição de disparo |
|---|---|
| `empty_bundle` | `rag_chunks == [] and semantic_facts == []` |
| `low_relevance` | `max(score for chunk in rag_chunks) < MIN_RELEVANCE_SCORE` (default 0.25) |
| `off_topic` | LLM gerou resposta mas validador detectou citação inválida ou ausente em afirmações factuais |

**`MIN_RELEVANCE_SCORE`** configurável via `.env`. SPEC-009 calibra esse threshold com base no dataset de eval.

**Mensagem de `suggestion`:** template por `intent` para guiar o usuário:
- `diary_lookup` → "Não encontrei entradas no diário sobre isso. Tente especificar uma data ou um termo mais amplo."
- `reference_lookup` → "Não tenho referência cadastrada sobre isso. Você pode estar pensando em outro contexto?"
- (etc; lista completa no código.)

---

### 6. Prompt Strategy

#### 6.1 Ordem das seções no prompt

```
[System]
Você é um sintetizador do Second Brain. Responda usando APENAS
informação das seções abaixo. Toda afirmação factual deve citar
o id da fonte entre colchetes, ex.: [chunk_de_001].
Se a evidência for fraca ou ausente, retorne NoEvidence.

[Documentos relevantes - RAG]
{rag_chunks formatados}

[Histórico recente da conversa]
{recent_episodic formatado}

[Fatos sobre o usuário]
{semantic_facts formatados}

[Contexto da sessão atual]
{working formatado}

[Intent detectado]: {intent}

[Pergunta do usuário]: {query}
```

**Justificativa da ordem:** RAG primeiro porque é a evidência mais "autoritativa". Working memory por último porque é a mais recente — LLMs tendem a reter melhor o que está próximo do final do prompt, e a query do usuário ancorada no working memory dá contexto imediato.

#### 6.2 Serialização de cada chunk RAG

```
[chunk_de_001] (collection=diario, source=Dia 11.docx, score=0.78)
Conteúdo: {content}
```

O `id` aparece **no início** para o LLM aprender a referenciá-lo.

#### 6.3 Serialização de Fact

```
[fact:f_42] (category=preference, score=0.91)
Conteúdo: {content}
```

#### 6.4 Orçamento de tokens

Conforme SPEC-MEM §5.2, o orquestrador já corta antes de entregar. O agente assume o bundle como definitivo — **não trunca mais**.

---

### 7. Modelo LLM

**Modelo default:** `mistral` (já instalado no ambiente da Luane via SPEC-003).

**Configuração via `.env`:**

```bash
OLLAMA_SYNTHESIS_MODEL=mistral
OLLAMA_SYNTHESIS_TEMPERATURE=0.3    # mais baixa que conversa livre; favorece ancoragem
OLLAMA_SYNTHESIS_MAX_TOKENS=1024
OLLAMA_SYNTHESIS_TIMEOUT_S=30
```

**Por que mistral:**
- Já presente no ambiente; zero atrito.
- 7B parâmetros — bom equilíbrio entre qualidade e latência local.
- Suporte razoável a structured output via Pydantic AI.

**Quando trocar (a decidir via SPEC-009):**
- Se Faithfulness em PT-BR for ruim → `qwen2.5:7b` ou `llama3.1:8b`.
- Se latência for o gargalo → modelo menor (mas risco de qualidade).

**Configurável é primordial** — não acoplar a um modelo específico.

---

### 8. Validador Pós-Geração (Faithfulness Leve)

Após o LLM gerar `SynthesisOutput`, antes de devolver, roda um validador determinístico:

```python
def validate(output: SynthesisOutput, bundle: ContextBundle) -> SynthesisOutput:
    if output.kind == "no_evidence":
        return output

    bundle_ids = collect_ids(bundle)  # ids de rag_chunks + fact:{id}
    cited_inline = extract_inline_ids(output.answer)  # regex [id]

    # 1) Citação inline aponta para id fora do bundle? → alucinação confirmada
    hallucinated = cited_inline - bundle_ids
    if hallucinated:
        return NoEvidence(
            kind="no_evidence",
            reason="off_topic",
            suggestion="Não consegui ancorar a resposta nas fontes disponíveis.",
            used_intent=output.used_intent,
        )

    # 2) Resposta longa sem citação? → soft warning, confidence cai
    word_count = len(output.answer.split())
    if word_count > 30 and not output.citations:
        output.confidence *= 0.5
        log_span_attribute("synthesis.uncited_long_answer", True)

    # 3) Citações em citations[] mas não inline? → consistência
    inline_set = set(cited_inline)
    listed_set = {c.chunk_id for c in output.citations}
    if inline_set != listed_set:
        log_span_attribute("synthesis.citation_mismatch", True)
        # Não falha hard; só registra para evals.

    return output
```

**Filosofia:** rejeitar alucinação confirmada (citação para id inexistente), tolerar imperfeições com queda de confidence. Sem retry no MVP — SPEC-009 mede e decide se vale.

---

### 9. Integração com Pydantic AI e Ollama

#### 9.1 Esqueleto do agente

```python
# src/agents/synthesis/llm_classifier.py

from pydantic_ai import Agent, PromptedOutput
from src.agents.synthesis.schemas import SynthesisResult

class PydanticAISynthesisLLM:
    def __init__(self, settings: Settings):
        self._agent = Agent(
            _build_model(settings),               # Ollama via endpoint OpenAI-compat (/v1)
            output_type=PromptedOutput(SynthesisResult),
            system_prompt=SYNTHESIS_SYSTEM_PROMPT,
        )
```

> **Nota de implementação — `PromptedOutput` em vez de tool-calling.**
> O default do Pydantic AI extrai output estruturado via *tool-calling*. Modelos
> locais servidos pelo Ollama (ex.: `mistral:7b`) declaram suporte a tools mas
> emitem a resposta como texto livre, fazendo o agente estourar
> `UnexpectedModelBehavior: Exceeded maximum retries for output validation`.
> `PromptedOutput(SynthesisResult)` injeta o JSON schema no prompt e parseia a
> resposta textual — funciona de forma portável entre modelos locais. A triagem
> (SPEC-005) mantém tool-calling puro porque roda em `qwen2.5:3b`, que cumpre o
> contrato de tools de forma confiável. O wrapper LLM vive em
> `synthesis/llm_classifier.py` (injetável); o núcleo `SynthesisAgent` roda
> offline sem ele.

O `SynthesisAgent` consome o wrapper acima via o Protocol `SynthesisLLM`:

```python
# src/agents/agent2_synthesis.py

from src.agents.synthesis.schemas import SynthesisOutput, SynthesisResult, NoEvidence

class SynthesisAgent:
    def __init__(self, llm: Optional[SynthesisLLM] = None, *, settings: Settings = None):
        self.settings = settings or get_settings()
        self._llm = llm                            # None → degrada para NoEvidence

    async def synthesize(
        self,
        query: str,
        bundle: ContextBundle,
    ) -> SynthesisOutput:
        # Pré-check: NoEvidence sem chamar LLM
        if not bundle.rag_chunks and not bundle.semantic_facts:
            return NoEvidence(
                reason="empty_bundle",
                suggestion=self._suggestion_for(bundle.metadata.get("intent")),
                used_intent=bundle.metadata.get("intent", "unknown"),
            )
        if self._max_relevance(bundle) < self.settings.min_relevance_score:
            return NoEvidence(
                reason="low_relevance",
                suggestion=self._suggestion_for(bundle.metadata.get("intent")),
                used_intent=bundle.metadata.get("intent", "unknown"),
            )

        # Sem LLM injetado: degrada para NoEvidence em vez de inventar
        if self._llm is None:
            return NoEvidence(reason="off_topic", used_intent=...)

        # Chamada ao wrapper LLM com bundle serializado
        prompt = self._render_prompt(query, bundle)
        result = await self._llm.synthesize(prompt)   # Protocol SynthesisLLM

        # Validação pós-geração
        return self._validate(result, bundle)
```

#### 9.2 Tolerância a falha do LLM

| Cenário | Comportamento |
|---|---|
| Ollama timeout | Retornar `NoEvidence(reason="off_topic", suggestion="LLM indisponível")` + span de erro |
| LLM retorna JSON inválido (Pydantic AI já retry 1x) | Após retry: `NoEvidence(reason="off_topic")` |
| LLM responde só com saudação sem usar bundle | Validador captura via "resposta longa sem citação" + queda de confidence |

---

### 10. Instrumentação OTel

```
span: agent2.synthesize
├── attributes: bundle_size_chunks, bundle_size_facts, max_relevance,
│               intent, output_kind (synthesis_result | no_evidence)
├── span: agent2.precheck
├── span: agent2.llm.generate
│   ├── attributes: model, latency_ms, tokens_in, tokens_out
└── span: agent2.validate
    ├── attributes: cited_inline, hallucinated_ids, citation_mismatch
```

Consumido por SPEC-009 para métricas de:
- **Faithfulness rate**: % de respostas onde `hallucinated_ids == 0`.
- **Citation density**: cited_inline / word_count médio.
- **NoEvidence rate** por intent.
- Latência p50/p95 da síntese.

---

### 11. Arquivos Impactados

| Arquivo | Operação | Notas |
|---|---|---|
| `src/agents/agent2_synthesis.py` | **Criar** | `SynthesisAgent` |
| `src/agents/synthesis/schemas.py` | **Criar** | Pydantic models §3 |
| `src/agents/synthesis/prompts.py` | **Criar** | System prompt + suggestions por intent |
| `src/agents/synthesis/validator.py` | **Criar** | Validador pós-geração §8 |
| `src/agents/synthesis/renderer.py` | **Criar** | Serializa `ContextBundle` para prompt §6 |
| `src/config.py` | Adicionar settings | `OLLAMA_SYNTHESIS_*`, `MIN_RELEVANCE_SCORE` |
| `.env.example` | Adicionar variáveis | conforme §7 |
| `tests/test_spec_006.py` | **Criar** | Cobertura §12 |
| `tests/fixtures/synthesis_bundles.py` | **Criar** | Bundles mockados para testes |

---

### 12. Plano de Testes

Testes operam sobre `ContextBundle` mockados — não exigem ChromaDB nem dados reais.

#### 12.1 Pré-check (sem LLM)
- `test_empty_bundle_returns_no_evidence` — sem chunks/facts → `NoEvidence(empty_bundle)`
- `test_low_relevance_returns_no_evidence` — max score < threshold → `NoEvidence(low_relevance)`
- `test_threshold_configurable_via_settings` — override via `.env`

#### 12.2 Renderer
- `test_rag_chunks_appear_first_in_prompt` — ordem das seções §6.1
- `test_chunk_id_appears_at_start_of_serialization` — formato §6.2
- `test_fact_id_uses_fact_prefix` — formato §6.3

#### 12.3 Validador (sem LLM — mocka output)
- `test_citation_to_unknown_id_returns_no_evidence` — alucinação confirmada
- `test_long_answer_without_citation_drops_confidence` — soft warning
- `test_inline_and_listed_citations_match` — consistência

#### 12.4 Integração (com LLM real — Ollama)
- `test_synthesize_real_bundle_produces_citations` — smoke; marca `@pytest.mark.ollama`
- `test_synthesize_handles_off_topic_query` — query desalinhada com bundle → NoEvidence ou confidence baixa

#### 12.5 OTel
- `test_otel_spans_emitted_per_phase` — span pai + filhos
- `test_attributes_include_output_kind` — auditoria

---

### 13. Política de Erro

| Cenário | Comportamento |
|---|---|
| `bundle` é `None` | `TypeError` (assinatura) |
| `query` vazia | `NoEvidence(empty_bundle, suggestion="Faça uma pergunta")` |
| Ollama timeout | Span de erro + `NoEvidence(off_topic, suggestion="LLM indisponível")` |
| Pydantic AI falha em validar output após retry | `NoEvidence(off_topic)` |
| Validador detecta citação para ID inexistente | Substitui output por `NoEvidence(off_topic)` |

---

### 14. Checklist de Aceite

#### Pré-implementação
- [x] Contrato de entrada (ContextBundle) referenciado (§2)
- [x] Schema de saída discriminado (§3)
- [x] Política de citação obrigatória definida (§4)
- [x] Política de NoEvidence com 3 razões (§5)
- [x] Prompt strategy detalhada (§6)
- [x] Modelo LLM justificado e configurável (§7)
- [x] Validador pós-geração formalizado (§8)
- [x] Spans OTel mapeados (§10)
- [x] Plano de testes com bundles mockados (§12)
- [ ] Spec revisada e aprovada para implementação

#### Implementação (futura)
- [ ] `src/agents/synthesis/` criado
- [ ] Schemas Pydantic + system prompt em PT-BR
- [ ] Renderer respeita ordem §6.1
- [ ] Validador detecta os 3 casos da §8
- [ ] `SynthesisAgent` integra Pydantic AI + Ollama
- [ ] Testes unitários verdes (sem Ollama)
- [ ] Smoke test com Ollama mistral
- [ ] Latência p95 < 5s para bundle típico (10 chunks)

---

### 15. Estimativa de Esforço

| Fase | Estimativa |
|---|---|
| Schemas Pydantic + system prompt | 1.5h |
| Renderer (serialização de bundle) | 1.5h |
| Pré-check + thresholds | 1h |
| Validador pós-geração | 2h |
| Integração Pydantic AI + Ollama | 1.5h |
| Bundles mockados + testes unitários | 2.5h |
| Instrumentação OTel | 1h |
| Smoke test Ollama + ajustes de prompt | 2h |
| **Total** | **~13h** |

---

### 16. Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Mistral 7B não consegue manter formato de citação `[id]` consistentemente | Média | Validador detecta; SPEC-009 mede e migra para modelo maior se necessário |
| Modelo local ignora tool-calling e responde texto livre (`Exceeded maximum retries`) | Alta | **Resolvido**: wrapper usa `PromptedOutput` (§9.1) — schema no prompt, sem tools |
| `MIN_RELEVANCE_SCORE` mal calibrado → NoEvidence em excesso ou alucinação em excesso | Alta | Default conservador (0.25); SPEC-009 calibra com dataset |
| Bundle grande estoura janela de contexto do modelo | Baixa | Orquestrador trunca antes (responsabilidade da SPEC-008) |
| Pydantic AI structured output falha com Ollama | Média | Retry interno; fallback NoEvidence; troca de modelo via .env |
| Validador rejeita respostas legítimas (falsos positivos de alucinação) | Média | Logs em OTel; SPEC-009 mede taxa de rejeição |

---

### 17. Dependências e Sequência

**Esta spec depende de:** SPEC-MEM (ContextBundle), SPEC-003-2 (Fact/ConversationRecord types), SPEC-004 (RAGChunk).

**Esta spec é pré-requisito de:**
- **SPEC-008** (Orquestrador) — instancia e invoca o `SynthesisAgent`.
- **SPEC-009** (Evals) — mede Faithfulness, Citation Density, NoEvidence rate.

**Atividade subsequente recomendada:** SPEC-008 (Orquestrador MVP), porque depois dela há **chat real testável end-to-end**.
