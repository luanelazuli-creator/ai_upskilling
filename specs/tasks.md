# Blueprint do Projeto: Second Brain (Spec-Driven Development)

## Lista de Atividades (`tasks.md`)

| ID | Atividade | Descrição Breve | Data de Criação | Status |
| :--- | :--- | :--- | :--- | :--- |
| **TASK-001** | Definição do Problema e Escopo da Arquitetura | Mapeamento inicial das fontes de dados, desenho dos agentes e estratégia de avaliação. | 2026-06-02 | ✅ Concluído |
| **TASK-002** | Pipeline de Ingestão e Preparação de Dados Locais | Exportação manual do Google Drive (.docx/.csv) para estrutura local em Markdown (.md). | 2026-06-02 | ✅ Concluído |
| **TASK-003** | Infraestrutura Base e Observabilidade (OTel) | Setup do repositório, Pydantic AI e OpenTelemetry (OTel) com exportação local. | 2026-06-02 | ✅ Concluído |
| **TASK-003-1** | Observabilidade Avançada e Setup Modular | Implementação de RAG local, memória persistente, guardrails de PII e scripts de conversão. | 2026-06-02 | ✅ Concluído |
| **TASK-004** | Implementação do RAG Local (Base de Conhecimento) | Configuração de banco vetorial local e mecanismos de busca semântica para as 3 pastas. | 2026-06-02 | Planejado |
| **TASK-005** | Desenvolvimento do Agente 1: Especialista em Contexto | Agente responsável por rotear, classificar a intenção e buscar dados temporais (Diário). | 2026-06-02 | Planejado |
| **TASK-006** | Desenvolvimento do Agente 2: Especialista em Síntese e RAG | Agente focado em consolidar manuais, cursos e criar resumos executivos estruturados. | 2026-06-02 | Planejado |
| **TASK-007** | Desenvolvimento do Agente 3: Especialista em Memória e Guardrails | Agente de persistência de preferências que higieniza PII e mantém contexto histórico. | 2026-06-02 | Planejado |
| **TASK-008** | Orquestração Multiagente e Interface de Usuário | Integração dos agentes usando padrões de design do Pydantic AI e criação de CLI/Interface simples. | 2026-06-02 | Planejado |
| **TASK-009** | Engenharia de Avaliação (Pydantic Evals) | Criação do dataset de teste rigoroso e métricas de aderência, alucinação e vazamento de PII. | 2026-06-02 | Planejado |
| **TASK-010** | Refinamento Baseado em Evidências e Relatório Final | Execução dos evals comparando Multiagente vs Chatbot Simples e geração do report da Capstone. | 2026-06-02 | Planejado |
