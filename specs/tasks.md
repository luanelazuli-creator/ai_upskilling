# Blueprint do Projeto: Second Brain (Spec-Driven Development)

## Lista de Atividades (`tasks.md`)

| ID | Atividade | Descrição Breve | Data de Criação | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TASK-001** | Definição do Problema e Escopo da Arquitetura | Mapeamento inicial das fontes de dados, desenho dos agentes e estratégia de avaliação. | 2026-06-02 | ✅ Concluído |
| **TASK-002** | Pipeline de Ingestão e Preparação de Dados Locais | Exportação manual do Google Drive (.docx/.csv) para estrutura local em Markdown (.md). | 2026-06-02 | ✅ Concluído |
| **TASK-003** | Infraestrutura Base e Observabilidade (OTel) | Setup do repositório, Pydantic AI e OpenTelemetry (OTel) com exportação local. | 2026-06-02 | ✅ Concluído |
| **TASK-003-1** | Observabilidade Avançada e Setup Modular | Implementação de RAG local, memória persistente, guardrails de PII e scripts de conversão. | 2026-06-02 | ✅ Concluído |
| **TASK-MEM** | Arquitetura de Memória (Transversal) | Spec transversal que reconcilia os 4 tiers de memória, define fronteira RAG vs Semantic e contratos de API. Pré-requisito de TASK-003-2 em diante. | 2026-06-05 | 📝 Spec Redigida |
| **TASK-003-2** | Migração dos Módulos de Memória Existentes | Refatorar `SemanticMemory` (JSON→ChromaDB) e `EpisodicMemory` (ganhar layer vetorial) conforme contratos da SPEC-MEM. | 2026-06-05 | 🧪 Implementado e testado (17 testes em test_spec_003_2.py; suite full 36/36) |
| **TASK-004** | RAG Local — Integração Completa com os 3 Domínios | Pré-processamento autoritativo (.docx/.csv/.xlsx → .md + frontmatter), chunking adaptativo por domínio, embedding plugável, re-indexação por hash SHA-256, sanitização de PII na ingestão. | 2026-06-05 | 🧪 Implementado e testado (dados fictícios; falta modelo multilingual real) |
| **TASK-005** | Agente 1: Triagem e Contexto Temporal | Roteador híbrido (regras + LLM fallback) com detecção de janela temporal via `dateparser`, política de clarificação, schema Pydantic discriminado. | 2026-06-05 | 🧪 Implementado e testado (30 testes em test_spec_005.py; núcleo offline regras+dateparser; LLM via Pydantic AI injetável) |
| **TASK-006** | Agente 2: Síntese e Resposta Ancorada | Sintetizador stateless: recebe ContextBundle, produz `SynthesisResult` (com citações inline obrigatórias) ou `NoEvidence` tipado. Validador pós-geração de faithfulness. Modelo `mistral` configurável. | 2026-06-05 | 📝 Spec Redigida |
| **TASK-007** | Desenvolvimento do Agente 3: Especialista em Memória e Guardrails | Agente de persistência de preferências que higieniza PII e mantém contexto histórico. | 2026-06-02 | Planejado |
| **TASK-008** | Orquestrador MVP — Pipeline Triagem → Retrieval → ContextBundle → Síntese | Coordenador stateful (1 processo = 1 sessão) que despacha TriageOutput, monta ContextBundle com orçamento de tokens, invoca SynthesisAgent, persiste turno via stub do Agente 3 e expõe CLI REPL. Implementa também `WorkingMemory` (SPEC-MEM §4.1). | 2026-06-05 | 📝 Spec Redigida |
| **TASK-009** | Engenharia de Avaliação (Pydantic Evals) | Criação do dataset de teste rigoroso e métricas de aderência, alucinação e vazamento de PII. | 2026-06-02 | Planejado |
| **TASK-010** | Refinamento Baseado em Evidências e Relatório Final | Execução dos evals comparando Multiagente vs Chatbot Simples e geração do report da Capstone. | 2026-06-02 | Planejado |
