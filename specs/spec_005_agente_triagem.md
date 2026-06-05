# Engenharia de Especificação: SPEC-005
## Agente 1 — Triagem e Contexto Temporal

**ID da Atividade:** TASK-005
**Data de Criação:** 05 de Junho de 2026
**Status:** 🟡 Em Refinamento
**Autor:** Desenvolvedor Capstone
**Depende de:** SPEC-MEM, SPEC-003-2, SPEC-004
**Consumido por:** SPEC-008 (Orquestrador)

---

### 1. Visão Geral

O **Agente 1 (Triagem)** é o primeiro a tocar cada mensagem do usuário. Sua função é **transformar uma query em linguagem natural em um plano de busca tipado**: qual intent, qual janela temporal, quais coleções RAG, quais tiers de memória.

**Características:**
- **Stateless** — não mantém estado interno; recebe contexto via parâmetros.
- **Rápido** — modelo LLM pequeno; regras determinísticas resolvem maioria dos casos.
- **Tipado** — saída é Pydantic discriminada (`TriageResult | ClarificationNeeded`).
- **Auditável** — emite span OTel com regras disparadas, confidence, reasoning.

#### Em escopo
- Classificação de intent (categorias fixas)
- Detecção de janela temporal via `dateparser` + LLM fallback
- Roteamento para coleções RAG (`diario`, `cursos`, `referencias`)
- Roteamento para tiers de memória (`episodic_recent`, `semantic`)
- Confidence scoring + política de clarificação
- Integração via Pydantic AI

#### Fora de escopo
- Execução das buscas (responsabilidade do orquestrador → Agente 2)
- Síntese de resposta (SPEC-006)
- Persistência (SPEC-007)
- Working Memory writes (o orquestrador escreve usando o output deste agente)

---

### 2. Categorias de Intent

Conjunto **fechado**. Toda query é classificada em exatamente uma categoria primária; intents secundárias são possíveis em `cross_domain`.

| Intent | Descrição | Exemplos | Roteamento default |
|---|---|---|---|
| `diary_lookup` | Consulta histórica do diário | "o que fiz dia 11", "atividades de junho" | RAG: `diario` + temporal_filter |
| `course_status` | Status/progresso de cursos | "onde parei no Data Engineer", "qual meu progresso" | RAG: `cursos` |
| `reference_lookup` | Manuais, stakeholders, glossário | "como pedir atestado", "quem é PM do projeto X" | RAG: `referencias` |
| `golden_prompt_request` | Pedido por template/prompt | "qual prompt usar para pesquisa", "tem template para Y" | RAG: `cursos` (filtro `type=golden_prompt`) |
| `user_profile` | Auto-referência | "quais minhas preferências", "o que você sabe de mim" | Memory: `semantic` |
| `conversation_recall` | Recall de conversa passada | "voltando ao que falamos sobre X", "lembra de Y" | Memory: `episodic_recent` + `episodic_semantic` |
| `cross_domain` | Combina múltiplos | "minha pendência do diário sobre o manual de Z" | RAG: múltiplas coleções |
| `meta` | Sobre o próprio agente | "o que você sabe fazer", "comandos" | Sem busca; resposta direta |
| `unclear` | Não classificável com confiança | "isso aí", "ok" | Dispara clarificação |

---

### 3. Schema de Saída (Pydantic, união discriminada)

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional, Union
from datetime import datetime

class TemporalRange(BaseModel):
    start: datetime
    end: datetime
    expression: str         # "semana passada", "junho de 2026"
    detection_method: Literal["dateparser", "llm", "explicit"]

class TriageResult(BaseModel):
    kind: Literal["triage_result"] = "triage_result"
    intent: Literal[
        "diary_lookup", "course_status", "reference_lookup",
        "golden_prompt_request", "user_profile", "conversation_recall",
        "cross_domain", "meta",
    ]
    target_rag_collections: list[Literal["diario", "cursos", "referencias"]]
    target_memory_tiers: list[Literal["episodic_recent", "episodic_semantic", "semantic"]]
    temporal_filter: Optional[TemporalRange] = None
    structured_filters: dict = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    classification_method: Literal["rules", "llm", "hybrid"]
    reasoning: str          # Para OTel; humano-legível

class ClarificationNeeded(BaseModel):
    kind: Literal["clarification_needed"] = "clarification_needed"
    reason: Literal["low_confidence", "multiple_intents", "missing_temporal"]
    question: str           # Pergunta gerada para o usuário
    detected_options: list[str]  # Opções consideradas (ajuda usuário a escolher)
    confidence: float

TriageOutput = Union[TriageResult, ClarificationNeeded]
```

**Discriminação:** o campo `kind` permite ao orquestrador despachar via Pydantic discriminated union sem `isinstance`.

---

### 4. Estratégia de Classificação (Híbrida)

#### 4.1 Camada 1 — Regras determinísticas

Primeira passada. Tenta classificar por **palavras-chave de domínio**. Se acertar com alta confiança, pula LLM.

**Regras propostas (não-exaustivo; ajustar via evals):**

| Regra | Palavras/padrões | Intent | Confidence base |
|---|---|---|---|
| Datas explícitas | `dia \d+`, `\d{2}/\d{2}`, "ontem", "hoje" | `diary_lookup` | 0.9 |
| Termos de diário | "diário", "atividade", "impedimento", "pendência" | `diary_lookup` | 0.85 |
| Termos de curso | "curso", "certificação", "trilha", "aprendizado", "onde parei" | `course_status` | 0.85 |
| Termos de manual | "como faço", "como pedir", "manual", "procedimento" | `reference_lookup` | 0.8 |
| Termos de stakeholder | "quem é", "responsável por", "contato de" | `reference_lookup` (cat=stakeholders) | 0.85 |
| Termos de glossário | "o que significa", "definição de" | `reference_lookup` (cat=glossario) | 0.8 |
| Golden prompt | "template", "prompt para", "qual prompt" | `golden_prompt_request` | 0.85 |
| Auto-referência | "minhas preferências", "o que sabe de mim", "quem sou" | `user_profile` | 0.9 |
| Recall conversacional | "voltando", "lembra", "como falei", "antes você disse" | `conversation_recall` | 0.85 |

**Combinação de regras:** se duas regras disparam de domínios diferentes, marcar como `cross_domain` (confidence cai para média dos hits).

#### 4.2 Camada 2 — LLM fallback (Pydantic AI + Ollama)

Quando regras não classificam com `confidence >= 0.7`:

```python
from pydantic_ai import Agent

triage_llm_agent = Agent(
    model=settings.ollama_triage_model,    # ver §7
    output_type=TriageResult,              # mesmo schema
    system_prompt="""Você é um classificador de intents para um Second Brain.
    Categorias disponíveis: [...]
    Coleções RAG: diario, cursos, referencias.
    Tiers de memória: episodic_recent, episodic_semantic, semantic.
    Retorne um TriageResult Pydantic.""",
)
```

LLM recebe a query + o resultado parcial das regras como hint. Output forçado para o mesmo `TriageResult`.

#### 4.3 Camada 3 — Decisão de clarificação

Se após camadas 1+2 o `confidence < 0.6` **ou** múltiplos intents foram detectados sem distinção clara, gera `ClarificationNeeded`. Política de geração da pergunta:

- `low_confidence`: "Não tenho certeza do que você está pedindo. Você quer (a) consultar seu diário, (b) ver progresso em cursos, ou (c) buscar uma referência?"
- `multiple_intents`: lista as opções detectadas para o usuário escolher.
- `missing_temporal`: "Você mencionou X, mas não disse de quando. Tem período em mente?"

---

### 5. Detecção de Janela Temporal

#### 5.1 Camada A — `dateparser` (Python lib)

```python
import dateparser
from dateparser.search import search_dates

# Detecta múltiplas expressões temporais em PT-BR
results = search_dates(
    user_message,
    languages=["pt"],
    settings={
        "PREFER_DATES_FROM": "past",
        "RELATIVE_BASE": datetime.now(),
    },
)
```

**Cobertura esperada:** "hoje", "ontem", "anteontem", "semana passada", "mês passado", "em junho", "dia 11", "11/06", "junho de 2026", "última segunda".

**Quando detectar intervalo (não ponto):**
- "semana passada" → intervalo de 7 dias
- "junho" → mês inteiro
- "dia 11" → dia inteiro (00:00 → 23:59:59)

Função `_expand_to_range(date, expression) → TemporalRange` faz essa expansão com regras explícitas.

#### 5.2 Camada B — LLM fallback

Para expressões que `dateparser` falha (ex: "antes do feriado", "logo depois do curso X"), o LLM é chamado com:

```python
temporal_llm_agent = Agent(
    model=settings.ollama_triage_model,
    output_type=TemporalRange,
    system_prompt="Extraia janela temporal da query. Data de referência: {now}.",
)
```

Se LLM também falhar (`output` inválido ou exceção), retorna `temporal_filter=None` e marca para o orquestrador decidir.

#### 5.3 Política `missing_temporal`

Se `intent == "diary_lookup"` mas nenhuma janela temporal foi detectada, dispara `ClarificationNeeded(reason="missing_temporal")`. Diário sem janela temporal seria buscar em toda a coleção — ruim para recall e custo.

**Exceção:** se a query contém termos como "tudo", "todos", "qualquer", aceita busca sem janela.

---

### 6. Política de Clarificação (UX)

Conforme decisão arquitetural, queries com `confidence < 0.6` **interrompem o flow** e devolvem pergunta ao usuário. Isso impacta o Orquestrador (SPEC-008):

- Quando recebe `ClarificationNeeded`, o orquestrador devolve a pergunta como resposta do turno atual.
- A próxima mensagem do usuário é re-roteada pelo Agente 1; o orquestrador injeta a query original como contexto:
  `<previous_unclear_query>` + `<user_clarification>`.
- Limite: **2 rodadas de clarificação consecutivas**. Após a 2ª, fallback amplo (busca tudo) com aviso ao usuário.

**Evita armadilha de UX:** se 3+ clarificações em sequência, usuário desiste — fallback é o caminho do "pelo menos tentamos".

---

### 7. Integração com Pydantic AI e Ollama

#### 7.1 Configuração (`.env`)

```bash
# Modelo de triagem (pequeno, rápido)
OLLAMA_TRIAGE_MODEL=qwen2.5:3b    # Alternativas: llama3.2:3b, phi3:mini
OLLAMA_TRIAGE_TEMPERATURE=0.1     # Baixa; classificação deve ser estável
OLLAMA_TRIAGE_TIMEOUT_S=10        # Triagem não pode ser lenta
```

**Critérios para escolha do modelo:**
- ≤ 4B parâmetros (latência < 2s em hardware típico)
- Bom em multilingual (PT-BR)
- Bom em structured output (Pydantic AI exige)

`qwen2.5:3b` foi escolhido como default por ter benchmarks consistentes em multilingual + structured. **Configurável** porque SPEC-009 pode mostrar que outro performa melhor neste use case.

#### 7.2 Esqueleto do agente (Pydantic AI)

```python
# src/agents/agent1_triage.py

class TriageAgent:
    def __init__(self, settings: Settings):
        self.rule_engine = TriageRuleEngine()       # camada 1
        self.llm_agent = Agent(                     # camada 2
            model=settings.ollama_triage_model,
            output_type=TriageOutput,
            ...
        )
        self.temporal_extractor = TemporalExtractor()  # dateparser + LLM

    async def triage(
        self,
        query: str,
        clarification_round: int = 0,
    ) -> TriageOutput:
        # Camada 1: regras
        rules_result = self.rule_engine.evaluate(query)
        if rules_result.confidence >= 0.7:
            triage = rules_result
        else:
            # Camada 2: LLM fallback (com hint das regras)
            triage = await self.llm_agent.run(query, deps=rules_result).output

        # Janela temporal (paralelo à classificação)
        triage.temporal_filter = await self.temporal_extractor.extract(query)

        # Política de clarificação
        if triage.confidence < 0.6 and clarification_round < 2:
            return self._build_clarification(triage, query)

        if (
            triage.intent == "diary_lookup"
            and triage.temporal_filter is None
            and not self._contains_all_marker(query)
            and clarification_round < 2
        ):
            return ClarificationNeeded(
                kind="clarification_needed",
                reason="missing_temporal",
                question="De qual período do diário você quer saber?",
                detected_options=["última semana", "este mês", "tudo"],
                confidence=triage.confidence,
            )

        return triage
```

---

### 8. Instrumentação OTel

Toda chamada de `triage()` gera **1 span pai** + **spans filhos** para visibilidade:

```
span: agent1.triage
├── attributes: query_length, confidence_final, intent, classification_method
├── span: agent1.rules.evaluate
│   ├── attributes: rules_fired, confidence
├── span: agent1.llm.classify          (se camada 2 acionada)
│   ├── attributes: model, latency_ms, tokens
├── span: agent1.temporal.dateparser
│   ├── attributes: expressions_found, success
└── span: agent1.temporal.llm          (se fallback)
```

Consumido por SPEC-009 para métricas de:
- Latência por camada
- % de queries resolvidas só por regras (alvo: ≥ 60% após tuning)
- Taxa de clarificação (alvo: ≤ 15%)
- Taxa de LLM fallback temporal (alvo: ≤ 20%)

---

### 9. Arquivos Impactados

| Arquivo | Operação | Notas |
|---|---|---|
| `src/agents/agent1_triage.py` | **Criar** | Classe `TriageAgent` orquestrando camadas |
| `src/agents/triage/rules.py` | **Criar** | `TriageRuleEngine` com tabela §4.1 |
| `src/agents/triage/temporal.py` | **Criar** | `TemporalExtractor` (dateparser + LLM) |
| `src/agents/triage/schemas.py` | **Criar** | Pydantic models §3 |
| `src/agents/triage/prompts.py` | **Criar** | System prompts para LLM fallback |
| `src/config.py` | Adicionar settings | OLLAMA_TRIAGE_* |
| `.env.example` | Adicionar variáveis | conforme §7.1 |
| `requirements.txt` | Adicionar `dateparser>=1.2.0` | — |
| `tests/test_spec_005.py` | **Criar** | Dataset + cobertura §10 |

---

### 10. Plano de Testes

#### 10.1 Dataset de queries (golden set)

Arquivo `tests/fixtures/triage_golden.yaml`:

```yaml
- query: "o que fiz no dia 11 de junho"
  expected_intent: diary_lookup
  expected_collections: [diario]
  expected_temporal: {start: "2026-06-11T00:00:00", end: "2026-06-11T23:59:59"}

- query: "onde parei no curso de Data Engineer"
  expected_intent: course_status
  expected_collections: [cursos]
  expected_filters: {course: "Data Engineer Certificate"}

- query: "quem é responsável pelo time de plataforma"
  expected_intent: reference_lookup
  expected_filters: {category: stakeholders}

- query: "ok"
  expected_kind: clarification_needed
  expected_reason: low_confidence

- query: "minha pendência do diário sobre o atestado"
  expected_intent: cross_domain
  expected_collections: [diario, referencias]
```

Tamanho inicial: ~30 queries cobrindo todos os intents + edge cases.

#### 10.2 Testes unitários

- `test_rules_classify_diary_with_explicit_date` — regra "dia X" dispara
- `test_rules_low_confidence_triggers_llm` — confidence < 0.7 chama LLM
- `test_dateparser_extracts_relative_dates_pt` — "semana passada" vira intervalo
- `test_dateparser_misses_falls_back_to_llm` — "antes do feriado" vai para LLM
- `test_cross_domain_detection` — regras de 2 domínios disparam → cross_domain
- `test_clarification_after_low_confidence` — confidence baixa → ClarificationNeeded
- `test_clarification_round_2_falls_back` — 2ª rodada sem clareza → fallback amplo
- `test_missing_temporal_in_diary_query_clarifies` — diary sem data dispara clarif.
- `test_all_marker_skips_temporal_clarification` — "tudo" permite query ampla
- `test_otel_span_emitted_per_layer` — todos os spans esperados aparecem

#### 10.3 Testes de integração

- `test_full_triage_pipeline_on_golden_dataset` — roda dataset YAML, mede % acerto
- Threshold mínimo no MVP: **80% de acerto de intent** + **90% de extração temporal**

---

### 11. Política de Erro

| Cenário | Comportamento |
|---|---|
| LLM Ollama timeout | Cair para confidence das regras + warning span; se < 0.6, clarificação |
| LLM retorna JSON inválido | Pydantic AI já retry interno (1x); se persiste, fallback rules + warning |
| `dateparser` retorna múltiplas datas conflitantes | Pegar a mais provável; logar todas; expression marca "ambiguous" |
| Query vazia ou só whitespace | Retornar imediatamente `ClarificationNeeded(reason="low_confidence")` sem chamar LLM |
| 3+ clarificações consecutivas | Forçar fallback amplo; resposta inclui aviso "vou buscar em todas as fontes" |

---

### 12. Checklist de Aceite

#### Pré-implementação
- [x] 9 intents catalogadas (§2)
- [x] Schema Pydantic discriminado definido (§3)
- [x] Tabela de regras com confidence base (§4.1)
- [x] Política de detecção temporal (§5)
- [x] Política de clarificação documentada (§6)
- [x] Modelo Ollama escolhido com justificativa (§7)
- [x] Spans OTel mapeados (§8)
- [x] Plano de testes com golden dataset (§10)
- [ ] Spec revisada e aprovada para implementação

#### Implementação (futura)
- [ ] Estrutura `src/agents/triage/` criada
- [ ] `TriageRuleEngine` cobrindo §4.1
- [ ] `TemporalExtractor` (dateparser + LLM fallback)
- [ ] `TriageAgent` integrando camadas
- [ ] Pydantic AI agent configurado com `output_type=TriageOutput`
- [ ] Modelo `qwen2.5:3b` baixado e validado
- [ ] Golden dataset com ≥ 30 entradas
- [ ] Testes ≥ 80% de acerto de intent
- [ ] Smoke: chat real com 5 queries variadas, todos os spans capturados

---

### 13. Estimativa de Esforço

| Fase | Estimativa |
|---|---|
| Implementar `TriageRuleEngine` + tabela de regras | 2h |
| Implementar `TemporalExtractor` (dateparser + LLM) | 2h |
| Schemas Pydantic + prompts | 1h |
| Integração Pydantic AI + Ollama (modelo triage) | 1.5h |
| Política de clarificação (estado de round) | 1h |
| Instrumentação OTel completa | 1h |
| Golden dataset + testes unitários | 2.5h |
| Testes de integração + threshold check | 1.5h |
| Smoke testing + ajustes finos | 1.5h |
| **Total** | **~14h** |

---

### 14. Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| `dateparser` falha sutilmente em expressões PT-BR coloquiais | Média | LLM fallback + dataset cobre casos comuns; iteração orientada por evals |
| Modelo `qwen2.5:3b` ruim em structured output PT-BR | Média | Modelo trocável via `.env`; SPEC-009 compara alternativas |
| Taxa de clarificação alta degrada UX | Média | Métrica monitorada (alvo ≤ 15%); regras ampliáveis via dataset |
| Regras explodirem em complexidade conforme intents crescem | Baixa | Tabela em arquivo dedicado (rules.py); cada regra tem teste |
| Pydantic AI mudar API (versão 0.8.1 atual) | Baixa | Pin de versão; smoke test após upgrades |

---

### 15. Dependências e Sequência

**Esta spec depende de:** SPEC-MEM, SPEC-003-2, SPEC-004.

**Esta spec é pré-requisito de:**
- **SPEC-006** (Agente 2) — consome `TriageResult` para saber onde buscar.
- **SPEC-008** (Orquestrador) — despacha `TriageOutput` (discriminated union).
- **SPEC-009** (Evals) — golden dataset desta spec é parte do dataset de avaliação total.

**Atividade subsequente recomendada:** SPEC-006 (Agente 2 — Síntese e RAG).
