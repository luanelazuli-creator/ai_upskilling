"""System prompt e templates de sugestão da síntese (SPEC-006 §6, §5).

System prompt em PT-BR; templates de `NoEvidence.suggestion` por intent
para guiar o usuário quando o bundle não cobre a pergunta.
"""

from __future__ import annotations

SYNTHESIS_SYSTEM_PROMPT = """Você é um sintetizador do Second Brain pessoal em português.

REGRAS OBRIGATÓRIAS:
1. Responda usando APENAS informação das seções fornecidas (Documentos, Fatos, Histórico, Sessão).
2. Toda afirmação factual deve citar a fonte entre colchetes, ex.: [chunk_de_001] ou [fact:f_42].
3. Múltiplas citações em sequência: [id_a][id_b] (sem vírgula).
4. NÃO invente IDs: cite apenas IDs que aparecem nas seções fornecidas.
5. Saudações, instruções genéricas e perguntas de clarificação NÃO precisam de citação.
6. Se a evidência for fraca, ausente ou desalinhada com a pergunta, responda com
   um texto curto reconhecendo que não há base suficiente — o sistema decidirá
   se trata como NoEvidence.

ESTRUTURA DA SAÍDA (SynthesisResult):
- answer: texto livre em PT-BR com citações inline [id].
- citations: lista de objetos Citation para cada id citado inline.
- confidence: 0.0 a 1.0. Use confiança baixa quando precisar inferir muito.
- used_intent: ecoe o intent informado em [Intent detectado].
"""


# Sugestões por intent quando o bundle vem vazio ou com relevância baixa (§5).
_SUGGESTION_BY_INTENT: dict[str, str] = {
    "diary_lookup": (
        "Não encontrei entradas no diário sobre isso. "
        "Tente especificar uma data ou um termo mais amplo."
    ),
    "course_status": (
        "Não localizei material desse curso nas referências indexadas. "
        "Você pode citar o nome do curso ou a certificação?"
    ),
    "reference_lookup": (
        "Não tenho referência cadastrada sobre isso. "
        "Talvez seja outro contexto — você pode dar mais detalhes?"
    ),
    "golden_prompt_request": (
        "Ainda não tenho um template cadastrado para esse caso. "
        "Descreva o objetivo do prompt e eu posso buscar algo aproximado."
    ),
    "user_profile": (
        "Ainda não aprendi fatos sobre isso. Você pode me contar agora "
        "e eu salvo para próximas conversas."
    ),
    "conversation_recall": (
        "Não encontrei essa conversa no histórico recente. "
        "Pode lembrar quando foi ou qual era o assunto?"
    ),
    "cross_domain": (
        "Não achei material suficiente em nenhuma das fontes para responder. "
        "Pode reformular ou indicar onde devo procurar?"
    ),
    "meta": (
        "Posso ajudar com diário, cursos e referências. "
        "Faça uma pergunta sobre essas fontes."
    ),
}

_SUGGESTION_DEFAULT = (
    "Não tenho material suficiente para responder com base nas fontes disponíveis."
)


def suggestion_for_intent(intent: str | None) -> str:
    """Devolve a sugestão de NoEvidence apropriada para o intent dado."""
    if not intent:
        return _SUGGESTION_DEFAULT
    return _SUGGESTION_BY_INTENT.get(intent, _SUGGESTION_DEFAULT)
