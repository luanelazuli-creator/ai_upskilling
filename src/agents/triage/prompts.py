"""System prompts e templates de clarificação da triagem (SPEC-005 §4.2 e §6)."""

from __future__ import annotations

TRIAGE_SYSTEM_PROMPT = """Você é um classificador de intents para um Second Brain pessoal em português.

Classifique a mensagem do usuário em EXATAMENTE um intent primário:
- diary_lookup: consulta ao diário pessoal (atividades, impedimentos, pendências).
- course_status: status ou progresso de cursos e certificações.
- reference_lookup: manuais, procedimentos, stakeholders, glossário.
- golden_prompt_request: pedido por um template/prompt reutilizável.
- user_profile: auto-referência ("o que você sabe de mim", "minhas preferências").
- conversation_recall: recuperar algo de uma conversa passada.
- cross_domain: combina mais de um domínio acima.
- meta: sobre o próprio agente ("o que você faz", "comandos").

Coleções RAG disponíveis: diario, cursos, referencias.
Tiers de memória: episodic_recent, episodic_semantic, semantic.

Regras de roteamento:
- diary_lookup → diario
- course_status, golden_prompt_request → cursos
- reference_lookup → referencias
- user_profile → semantic
- conversation_recall → episodic_recent + episodic_semantic
- meta → sem busca

Retorne um TriageResult. Seja conservador na confiança: se a query for vaga
ou ambígua, use confidence baixa (< 0.6) para que o sistema peça esclarecimento.
classification_method deve ser "llm".
"""

TEMPORAL_SYSTEM_PROMPT = """Extraia a janela temporal mencionada na mensagem do usuário.
Data de referência (hoje): {now}.
Se houver uma expressão temporal (ex.: "antes do feriado", "logo depois do curso"),
retorne um TemporalRange com start, end, a expressão original e detection_method="llm".
Se NÃO houver nenhuma referência temporal, retorne null.
"""


# Templates de pergunta de clarificação por razão (SPEC-005 §4.3 / §6).
CLARIFICATION_TEMPLATES: dict[str, str] = {
    "low_confidence": (
        "Não tenho certeza do que você está pedindo. Você quer (a) consultar seu "
        "diário, (b) ver progresso em cursos, ou (c) buscar uma referência?"
    ),
    "multiple_intents": (
        "Entendi mais de uma intenção na sua mensagem. Qual delas você quer primeiro?"
    ),
    "missing_temporal": (
        "De qual período do diário você quer saber?"
    ),
}

CLARIFICATION_DEFAULT_OPTIONS: dict[str, list[str]] = {
    "low_confidence": ["consultar o diário", "ver progresso em cursos", "buscar uma referência"],
    "missing_temporal": ["última semana", "este mês", "tudo"],
}


def clarification_question(reason: str) -> str:
    return CLARIFICATION_TEMPLATES.get(reason, CLARIFICATION_TEMPLATES["low_confidence"])


def clarification_options(reason: str) -> list[str]:
    return list(CLARIFICATION_DEFAULT_OPTIONS.get(reason, []))
