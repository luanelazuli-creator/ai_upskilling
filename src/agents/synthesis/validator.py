"""Validador pós-geração (SPEC-006 §8) — faithfulness leve, determinístico.

Roda APÓS a LLM produzir um `SynthesisResult`. Três casos:
    1. Alucinação confirmada: citação inline para id fora do bundle
       → substitui por `NoEvidence(reason="off_topic")`.
    2. Resposta longa sem citações: soft warning, `confidence *= 0.5`.
    3. Inconsistência inline vs lista de citations: log-only (não falha).

Filosofia: rejeita alucinação confirmada; tolera imperfeição com queda
de confidence. Sem retry no MVP — SPEC-009 mede e decide se vale.
"""

from __future__ import annotations

import re
from typing import Optional

from opentelemetry.trace import Span

from src.memory.context_bundle import ContextBundle

from .prompts import suggestion_for_intent
from .renderer import collect_bundle_ids
from .schemas import NoEvidence, SynthesisOutput, SynthesisResult

# Citações inline são `[id]` onde id contém letras, dígitos, `_`, `-`, `:`.
# `:` é necessário para `fact:f_42` (SPEC-006 §4.1).
_INLINE_CITATION_RE = re.compile(r"\[([A-Za-z0-9_:\-]+)\]")

# Limiar de "resposta longa" para warning de ausência de citação (§4.3 / §8).
_LONG_ANSWER_WORDS = 30


def extract_inline_ids(answer: str) -> list[str]:
    """Extrai todos os ids citados inline em `[id]`, preservando ordem.

    Duplicatas são mantidas (o validador costuma comparar como set, mas
    métricas podem precisar da contagem exata).
    """
    if not answer:
        return []
    return _INLINE_CITATION_RE.findall(answer)


def validate(
    output: SynthesisOutput,
    bundle: ContextBundle,
    span: Optional[Span] = None,
) -> SynthesisOutput:
    """Pós-processa a saída da LLM, devolvendo `SynthesisOutput` final.

    - `NoEvidence` retorna inalterado (já foi decidido antes ou em outro caminho).
    - `SynthesisResult` é inspecionado:
        * citação inline para id fora do bundle → NoEvidence(off_topic).
        * resposta longa sem citações → confidence *= 0.5.
        * inline vs citations[] diferentes → log-only.
    """
    if output.kind == "no_evidence":
        return output

    assert isinstance(output, SynthesisResult)  # ajuda o type-checker

    bundle_ids = collect_bundle_ids(bundle)
    inline_ids = extract_inline_ids(output.answer)
    inline_set = set(inline_ids)

    # 1) Alucinação confirmada: ids inline que não pertencem ao bundle.
    hallucinated = inline_set - bundle_ids
    if span is not None:
        _safe_set_attr(span, "synthesis.cited_inline", len(inline_set))
        _safe_set_attr(span, "synthesis.hallucinated_ids", len(hallucinated))

    if hallucinated:
        return NoEvidence(
            reason="off_topic",
            suggestion=suggestion_for_intent(output.used_intent)
            or "Não consegui ancorar a resposta nas fontes disponíveis.",
            used_intent=output.used_intent,
        )

    # 2) Resposta longa sem citações → soft warning.
    word_count = len(output.answer.split())
    if word_count > _LONG_ANSWER_WORDS and not output.citations:
        output = output.model_copy(update={"confidence": output.confidence * 0.5})
        if span is not None:
            _safe_set_attr(span, "synthesis.uncited_long_answer", True)

    # 3) Consistência inline vs citations[] → log-only.
    listed_set = {c.chunk_id for c in output.citations}
    if inline_set and listed_set and inline_set != listed_set:
        if span is not None:
            _safe_set_attr(span, "synthesis.citation_mismatch", True)

    return output


def _safe_set_attr(span: Span, key: str, value) -> None:
    """OTel `set_attribute` tolerante (alguns valores podem não ser primitivos)."""
    try:
        span.set_attribute(key, value)
    except Exception:
        # Atributos de telemetria nunca devem derrubar o turno.
        return
