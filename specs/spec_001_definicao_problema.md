# Engenharia de Especificação: SPEC-001
## Definição do Problema e Escopo da Arquitetura Inicial

**ID da Atividade:** TASK-001  
**Data de Criação:** 02 de Junho de 2026  
**Status:** Concluído (Fase de Desenho)  
**Autor:** Desenvolvedor Capstone  

---

### 1. Visão Geral do Problema
O objetivo deste projeto é construir um ecossistema de **Segundo Cérebro (Second Brain)** focado em produtividade pessoal, gestão de conhecimento e rotinas de trabalho. O sistema resolverá a fragmentação de informações históricas através de um padrão de desenvolvimento estritamente guiado por especificações e avaliações (**Spec-Driven & Eval-Driven Development**).

Diferente de um chatbot comercial genérico, este sistema deve provar matematicamente (via métricas de avaliação) que uma arquitetura multiagente com RAG local e gerenciamento de memória persistente supera uma abordagem linear de prompt único.

---

### 2. Arquitetura de Dados (Fontes Locais)
A estratégia inicial consiste em cargas manuais de arquivos extraídos do Google Drive para um diretório local interno (`/capstone/data/`). Os dados são categorizados em três grandes domínios com características distintas:

* **Domínio 1: Diário (`/data/diario/YYYY/MM/`)**
    * *Dinâmica:* Altamente incremental e cronológica (arquivos diários).
    * *Conteúdo:* Atividades trabalhadas, impedimentos, decisões do dia a dia e pendências.
    * *Formato:* Inicialmente `.docx` / `.csv`, migrando para `.md`.
* **Domínio 2: Cursos (`/data/cursos/`)**
    * *Dinâmica:* Semi-estática. Updates ocorrem conforme evolução em trilhas de aprendizado.
    * *Conteúdo:* Status de progresso ("onde parei"), insights profundos e *Golden Prompts*.
* **Domínio 3: Referências (`/data/referencias/`)**
    * *Dinâmica:* Estática/Referencial.
    * *Conteúdo:* Manuais corporativos (ponto eletrônico, envio de atestados), mapeamento de stakeholders chaves da empresa, contatos interdepartamentais e um glossário técnico individual.

---

### 3. Design Multiagente (Pydantic AI)
Para atender ao requisito mínimo de 3 agentes especializados colaborativos, a arquitetura será dividida em:

```
                  [ Interface do Usuário (CLI) ]
                                |
                                v
               [ Agente 1: Triagem & Contexto Temporal ]
                                |
         +----------------------+----------------------+
         |                                             |
         v                                             v
[ Agente 2: Sintetizador & RAG ]        [ Agente 3: Memória & Guardrails ]
         |                                             |
 (Busca Semântica Local)                        (Sanitização PII e)
 (Diário, Cursos, Manuais)                      (Preferências de Uso)
```

1.  **Agente 1: Triagem e Contexto Temporal (Routing Agent)**
    * *Função:* Analisa a intenção da mensagem do usuário. Identifica se a pergunta exige contexto histórico temporal (Diário), consulta de regras estáveis (Referências) ou status de aprendizado (Cursos).
2.  **Agente 2: Sintetizador de Conhecimento e RAG (Knowledge Agent)**
    * *Função:* Executa buscas semânticas vetoriais agressivas no RAG local. Cruza dados de categorias diferentes (ex: correlacionar uma pendência do diário com um manual de referência) e formata a resposta técnica estruturada.
3.  **Agente 3: Curador de Memória e Guardrails (Privacy & State Agent)**
    * *Função:* Mantém a memória de longo prazo do usuário (ex: "o usuário prefere respostas compactas"). Antes de persistir qualquer dado no histórico ou memória secundária, roda um pipeline de **Guardrail para remoção de PII** (anonymizing telefones, CPFs, nomes de clientes sensíveis).

---

### 4. Estratégia de Avaliação (Pydantic Evals)
O coração do desenvolvimento orientado a especificações. Criaremos um ambiente de teste automatizado que rodará a cada mudança no código:

* **Métricas de RAG:** Context Relevance (o agente buscou os arquivos certos do diário?) e Faithfulness (a resposta gerada possui alucinações ou está estritamente ancorada nos documentos?).
* **Métricas de Privacidade:** Taxa de vazamento de PII (Garantir que 100% de dados sensíveis sejam sanitizados pelo Agente 3).
* **Comparativo Baseline:** O sistema rodará os mesmos prompts de teste em um pipeline simples (Single-Agent RAG) e computará a diferença de score para provar o ganho real da arquitetura multiagente.

---

### 5. Observabilidade Local (OTel)
Para auditoria de chamadas e inspeção dos pensamentos internos dos agentes (*agentic reasoning*):
* Implementação do OpenTelemetry nativo do Pydantic AI.
* Visualização de traces de forma local (utilizando ferramentas como Arize Phoenix, Langfuse local ou simplesmente dump estruturado de console) sem tráfego de dados para a nuvem externa.
