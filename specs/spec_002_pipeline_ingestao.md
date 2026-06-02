# Engenharia de Especificação: SPEC-002
## Pipeline de Ingestão e Preparação de Dados Locais

**ID da Atividade:** TASK-002  
**Data de Criação:** 02 de Junho de 2026  
**Status:** ✅ Concluído (Dados Ingeridos)  
**Autor:** Desenvolvedor Capstone  

---

### 1. Visão Geral
Pipeline de ingestão de dados do Google Drive para estrutura local, organizando múltiplos formatos (.docx, .xlsx, .md) para otimização no RAG local (Pydantic AI + vetorização). Os dados foram exportados manualmente e organizados em três domínios principais.

---

### 2. Estrutura de Pastas e Dados Ingeridos

#### 2.1 Diário (Temporal / Cronológico)
**Localização:** `/ai_engineer_upskill/data/diario/YYYY/MM/`

**Estrutura Real:**
```
data/diario/
  ├── 2026/
  │   ├── 01/                         (vazio, sem dados)
  │   ├── 02-05/                      (vazios, sem dados)
  │   └── 06/
  │       ├── Dia 11 - Keep Studying.docx
  │       └── Dia 12 - Studying MCP.docx
```

**Formato Atual:**
- **Nomenclatura:** `Dia {DD} - {Descrição}.docx`
- **Conteúdo:** Atividades diárias, impedimentos, decisões, pendências
- **Status:** Arquivos .docx brutos (conversão para .md planejada em TASK-003)

#### 2.2 Cursos (Semi-estático / Aprendizado)
**Localização:** `/ai_engineer_upskill/data/cursos/`

**Estrutura Real:**
```
data/cursos/
  ├── Cursos Feitos.xlsx               (histórico de cursos completados)
  ├── Data Engineer Certificate.docx   (certificado e progresso)
  └── Golden Prompts/
      ├── Markdown convertion.docx     (exemplos de conversão)
      └── prompt_pesquisa_academica.md (golden prompt template)
```

**Formato Atual:**
- **Arquivos:** Misto (Excel, Word, Markdown)
- **Conteúdo:** Status de progresso, certificados, golden prompts reutilizáveis
- **Status:** Dados brutos em múltiplos formatos

#### 2.3 Referências (Estático / Consulta)
**Localização:** `/ai_engineer_upskill/data/referencias/`

**Estrutura Real:**
```
data/referencias/
  ├── Acessos sistemas.docx            → [manuais]
  ├── Atestados.docx                   → [manuais]
  ├── Glossário.xlsx                   → [glossario]
  ├── Links Úteis.xlsx                 → [procedimentos]
  ├── Pessoas Importantes.xlsx          → [stakeholders]
  └── Thoughtworks contacts.xlsx        → [stakeholders]
```

**Formato Atual:**
- **Nomenclatura:** Descritiva em português
- **Formatos:** Excel, Word (não seguem padrão .md)
- **Conteúdo:** Manuais, contatos, glossário técnico
- **Status:** Dados brutos em planilhas e documentos

---

### 3. Processo de Ingestão e Conversão (Executado)

#### Fase 1: Extração do Google Drive ✅
- Exportação manual de dados do Google Drive para `/ai_engineer_upskill/data/`
- Formatos capturados: `.docx`, `.xlsx`, `.md`
- Integridade validada

#### Fase 2: Organização Estruturada ✅
- Diário: Arquivos agrupados em `2026/MM/` (nomenclatura: `Dia DD - Descrição.docx`)
- Cursos: Arquivos consolidados em raiz + subpasta `Golden Prompts/`
- Referências: Arquivos categorizados implicitamente pelo nome

#### Fase 3: Conversão para Markdown (Próxima em TASK-003)
**Requerimentos de Conversão:**
- `.docx` → `.md` (usando Pandoc ou equivalente)
- `.xlsx` → `.md` tabelas ou listas estruturadas
- Manter estrutura de cabeçalhos (H1, H2, H3)
- Limpar metadados desnecessários

**Exemplo de Conversão Planejada:**
```
Entrada: "Dia 11 - Keep Studying.docx"
Saída: "2026-06-11_keep_studying.md" (ou renomeação a definir)
```

#### Fase 4: Sanitização de PII ✅ (Verificação Manual)
- Conferir ausência de CPFs, telefones, dados sensíveis
- Arquivo `Pessoas Importantes.xlsx` e `Thoughtworks contacts.xlsx` requerem revisão
- Sanitização adicional será executada pelo Agente 3 em runtime

#### Fase 5: Aplicação de Frontmatter (Próxima em TASK-003)
Cada arquivo `.md` receberá cabeçalho YAML minimalista:

**Diário:**
```yaml
---
date: 2026-06-11
source_file: "Dia 11 - Keep Studying.docx"
type: diario
tags: [keep_studying, mcp]
---
```

**Cursos:**
```yaml
---
course: Data Engineer Certificate
status: em_andamento
last_updated: 2026-06-02
type: course
source_file: "Data Engineer Certificate.docx"
---
```

**Referências:**
```yaml
---
category: manuais | stakeholders | glossario | procedimentos
source_file: "Acessos sistemas.docx"
last_reviewed: 2026-06-02
type: reference
---
```

---

### 4. Checklist de Validação

#### Dados Já Ingeridos ✅
- [x] Todos os arquivos exportados do Google Drive
- [x] Estrutura de pastas criada em `/ai_engineer_upskill/data/`
- [x] Formatos diversos (.docx, .xlsx, .md) organizados
- [x] Nenhum arquivo duplicado

#### Próximas Validações (TASK-003)
- [ ] Todos os arquivos em UTF-8
- [ ] Sem caracteres especiais corruptos
- [ ] Cabeçalhos markdown (H1, H2, H3) bem aninhados após conversão
- [ ] Links internos funcionam após conversão
- [ ] Frontmatter YAML válido
- [ ] PII sanitizado ou marcado para revisão manual

---

### 5. Resumo de Dados Ingeridos

| Domínio | Quantidade | Formatos | Status |
|---------|-----------|----------|--------|
| **Diário** | 2 arquivos | .docx | Aguardando conversão para .md |
| **Cursos** | 3 itens | .xlsx, .docx, .md | Misto (alguns já em .md) |
| **Referências** | 6 arquivos | .docx, .xlsx | Aguardando conversão para .md |
| **Total** | 11 itens | Múltiplos | Prontos para conversão |

---

### 6. Próximos Passos (TASK-003)

A TASK-003 (Infraestrutura Base e Observabilidade) executará:

1. **Conversão de Formatos**
   - Pandoc: `.docx` → `.md`
   - Pandas/Tabulate: `.xlsx` → `.md` tabelas

2. **Aplicação de Frontmatter**
   - Adicionar YAML headers conforme tipo (diário, course, reference)

3. **Indexação Vetorial**
   - Embedding Model local (SentenceTransformers ou similar)
   - Banco de dados vetorial (Chroma, Weaviate ou Qdrant)
   - Pipeline de busca semântica (RAG retriever)

4. **Observabilidade**
   - OpenTelemetry (OTel) para rastreamento
   - Logs estruturados de ingestão

---

### 7. Cronograma

- **Fase 1-5 (TASK-002):** ✅ 02 de Junho — Ingestão e organização concluída
- **Fase 3-6 (TASK-003):** 03 de Junho — Conversão, indexação e observabilidade
- **Status final:** Pronto para RAG e agentes

